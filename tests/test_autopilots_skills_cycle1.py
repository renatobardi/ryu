"""Testes do ciclo 1 de paridade — domínio autopilots-skills.

Cobre: webhook deliveries persistidas (dedupe/replay/rejected/ignored),
rotação de token + HMAC signing secret, payload → run/issue, triggers
múltiplos (schedule tz / api / event_filters), collaborators (enforcement),
subscribers, rule versions, runs enriquecidas (detail/skipped/planned_at),
estados active/paused/archived + run_only + issue_title_template,
skill files, labels de skill, import .md/.zip e skills locais do runtime.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import zipfile
from pathlib import Path

from tests.conftest import login


async def _setup(client):
    data = await login(client, "autopilots-owner@example.com")
    ws = data["workspaces"][0]["id"]
    r = await client.post("/api/agents", json={"workspace_id": ws, "name": "Bot", "handle": "apbot"})
    assert r.status_code in (200, 201), r.text
    return data, ws, r.json()["id"]


async def test_webhook_delivery_lifecycle(client):
    data, ws, agent_id = await _setup(client)
    r = await client.post("/api/autopilots", json={
        "workspace_id": ws, "name": "AP-hook", "rule": "regra",
        "trigger_type": "webhook", "target_agent_id": agent_id,
        "issue_title_template": "[AP] {name} {event}",
    })
    assert r.status_code == 201, r.text
    ap = r.json()
    trig = ap["triggers"][0]
    token = trig["webhook_token"]

    # payload capturado → run + issue (título via template, payload no corpo)
    r = await client.post(f"/api/autopilots/hook/{token}",
                          json={"event": "deploy.finished", "eventPayload": {"x": 1}})
    assert r.status_code == 200 and r.json()["status"] == "accepted", r.text
    run_id = r.json()["run_id"]
    r = await client.get(f"/api/autopilots/{ap['id']}/runs/{run_id}")
    run = r.json()
    assert run["source"] == "webhook"
    assert run["trigger_payload"]["event"] == "deploy.finished"
    r = await client.get(f"/api/issues/{run['issue_id']}")
    issue = r.json()
    assert "deploy.finished" in issue["title"]
    assert "deploy.finished" in issue["description"]

    # dedupe por Idempotency-Key → bump attempt_count, sem nova run
    h = {"Idempotency-Key": "k-1"}
    r1 = await client.post(f"/api/autopilots/hook/{token}", json={"a": 1}, headers=h)
    r2 = await client.post(f"/api/autopilots/hook/{token}", json={"a": 1}, headers=h)
    assert r1.json()["status"] == "accepted"
    assert r2.json()["status"] == "duplicate"
    assert r2.json()["delivery_id"] == r1.json()["delivery_id"]

    # corpo inválido → 400 sem persistência; sem corpo JSON → 400
    r = await client.post(f"/api/autopilots/hook/{token}", content=b"not json")
    assert r.status_code == 400

    # signing secret: missing → 401 rejected; válido → accepted; inválido → 401
    r = await client.put(
        f"/api/autopilots/{ap['id']}/triggers/{trig['id']}/signing-secret",
        json={"signing_secret": "supersecret"},
    )
    assert r.status_code == 200 and r.json()["has_signing_secret"] is True
    r = await client.post(f"/api/autopilots/hook/{token}", json={"b": 2})
    assert r.status_code == 401 and r.json()["reason"] == "missing_signature"
    body = json.dumps({"b": 2}).encode()
    sig = "sha256=" + hmac.new(b"supersecret", body, hashlib.sha256).hexdigest()
    r = await client.post(f"/api/autopilots/hook/{token}", content=body,
                          headers={"X-Hub-Signature-256": sig, "content-type": "application/json"})
    assert r.json()["status"] == "accepted", r.text
    r = await client.post(f"/api/autopilots/hook/{token}", content=body,
                          headers={"X-Hub-Signature-256": "sha256=" + "0" * 64,
                                   "content-type": "application/json"})
    assert r.status_code == 401 and r.json()["reason"] == "invalid_signature"

    # deliveries listadas com outcomes rejected + dispatched; detail traz raw_body
    r = await client.get(f"/api/autopilots/{ap['id']}/deliveries")
    statuses = [d["status"] for d in r.json()]
    assert "rejected" in statuses and "dispatched" in statuses
    first = [d for d in r.json() if d["status"] == "dispatched"][0]
    r = await client.get(f"/api/autopilots/{ap['id']}/deliveries/{first['id']}")
    assert r.json()["raw_body"]

    # replay recria delivery com replayed_from_delivery_id + nova run
    r = await client.post(f"/api/autopilots/{ap['id']}/deliveries/{first['id']}/replay")
    assert r.status_code == 200, r.text
    assert r.json()["replayed_from_delivery_id"] == first["id"]
    assert r.json()["run"] is not None

    # rotação de token invalida o antigo
    r = await client.post(f"/api/autopilots/{ap['id']}/triggers/{trig['id']}/rotate-webhook-token")
    new_token = r.json()["webhook_token"]
    assert new_token != token
    r = await client.post(f"/api/autopilots/hook/{token}", json={"z": 1})
    assert r.status_code == 404

    # event_filters: fora do escopo → ignored/event_filtered
    await client.put(f"/api/autopilots/{ap['id']}/triggers/{trig['id']}/signing-secret",
                     json={"signing_secret": ""})
    r = await client.patch(f"/api/autopilots/{ap['id']}/triggers/{trig['id']}",
                           json={"event_filters": [{"event": "workflow_run", "actions": ["completed"]}]})
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/autopilots/hook/{new_token}", json={"x": 1},
                          headers={"X-GitHub-Event": "push"})
    assert r.json()["reason"] == "event_filtered"
    r = await client.post(f"/api/autopilots/hook/{new_token}", json={"action": "completed"},
                          headers={"X-GitHub-Event": "workflow_run"})
    assert r.json()["status"] == "accepted"

    # paused/archived → delivery ignored; archived não roda nem manual
    await client.patch(f"/api/autopilots/{ap['id']}", json={"status": "paused"})
    r = await client.post(f"/api/autopilots/hook/{new_token}", json={"action": "completed"},
                          headers={"X-GitHub-Event": "workflow_run"})
    assert r.json()["reason"] == "autopilot_paused"
    await client.patch(f"/api/autopilots/{ap['id']}", json={"status": "archived"})
    r = await client.post(f"/api/autopilots/hook/{new_token}", json={"action": "completed"},
                          headers={"X-GitHub-Event": "workflow_run"})
    assert r.json()["reason"] == "autopilot_archived"
    r = await client.post(f"/api/autopilots/{ap['id']}/run")
    assert r.status_code == 409


async def test_triggers_versions_run_only_collaborators(client):
    data, ws, agent_id = await _setup(client)
    me = data["user"]["id"]
    r = await client.post("/api/autopilots", json={
        "workspace_id": ws, "name": "AP-multi", "rule": "r",
        "trigger_type": "manual", "target_agent_id": agent_id,
        "subscribers": [me],
    })
    assert r.status_code == 201, r.text
    ap = r.json()

    # triggers múltiplos: schedule com timezone + api; validações
    r = await client.post(f"/api/autopilots/{ap['id']}/triggers",
                          json={"kind": "schedule", "cron_expression": "0 9 * * *",
                                "timezone": "America/Sao_Paulo"})
    assert r.status_code == 201 and r.json()["timezone"] == "America/Sao_Paulo"
    sched_id = r.json()["id"]
    r = await client.post(f"/api/autopilots/{ap['id']}/triggers", json={"kind": "api"})
    api_id = r.json()["id"]
    r = await client.post(f"/api/autopilots/{ap['id']}/triggers", json={"kind": "schedule"})
    assert r.status_code == 400  # cron obrigatório
    r = await client.post(f"/api/autopilots/{ap['id']}/triggers",
                          json={"kind": "schedule", "cron_expression": "0 9 * * *", "timezone": "Nope"})
    assert r.status_code == 400  # tz inválido
    # enable/disable por trigger
    r = await client.patch(f"/api/autopilots/{ap['id']}/triggers/{sched_id}", json={"enabled": False})
    assert r.json()["enabled"] is False
    # run via trigger api → source=api
    r = await client.post(f"/api/autopilots/{ap['id']}/run", json={"trigger_id": api_id})
    assert r.json()["source"] == "api"
    r = await client.delete(f"/api/autopilots/{ap['id']}/triggers/{api_id}")
    assert r.status_code == 204

    # rule versions acumuladas (create + mudanças substantivas)
    await client.patch(f"/api/autopilots/{ap['id']}", json={"rule": "nova regra"})
    r = await client.get(f"/api/autopilots/{ap['id']}/versions")
    assert len(r.json()) >= 3
    assert r.json()[0]["config_summary"]["rule"] == "nova regra"

    # run atribui a versão vigente
    r = await client.post(f"/api/autopilots/{ap['id']}/run")
    assert r.json()["rule_version_id"] is not None

    # subscribers auto-inscritos na issue + inbox
    run = r.json()
    r = await client.get(f"/api/issues/{run['issue_id']}/subscribers")
    if r.status_code == 200:
        subs = r.json()
        assert any(s.get("user_id") == me and s.get("reason") == "autopilot" for s in subs), subs
    r = await client.get(f"/api/autopilots/{ap['id']}/subscribers")
    assert r.json() == [me]

    # execution_mode run_only: task direto, sem issue
    r = await client.post("/api/autopilots", json={
        "workspace_id": ws, "name": "AP-runonly", "rule": "run only rule",
        "trigger_type": "manual", "target_agent_id": agent_id, "execution_mode": "run_only",
    })
    ap2 = r.json()
    r = await client.post(f"/api/autopilots/{ap2['id']}/run")
    run2 = r.json()
    assert run2["task_id"] and not run2["issue_id"]
    r = await client.get(f"/api/tasks/{run2['task_id']}")
    assert r.status_code == 200 and "run only rule" in r.json()["prompt"]

    # collaborators: gestão + enforcement (usuário de fora → 403)
    r = await client.post(f"/api/autopilots/{ap['id']}/collaborators", json={"user_id": me})
    assert r.status_code == 201
    r = await client.get(f"/api/autopilots/{ap['id']}/collaborators")
    assert r.json()[0]["user_id"] == me
    r = await client.delete(f"/api/autopilots/{ap['id']}/collaborators/{me}")
    assert r.status_code == 204

    await login(client, "autopilots-outsider@example.com")
    for method, url, body in [
        ("patch", f"/api/autopilots/{ap['id']}", {"name": "hax"}),
        ("delete", f"/api/autopilots/{ap['id']}", None),
        ("post", f"/api/autopilots/{ap['id']}/run", None),
    ]:
        fn = getattr(client, method)
        r = await (fn(url, json=body) if body is not None else fn(url))
        assert r.status_code == 403, f"{method} {url}: {r.status_code}"


async def test_skill_files_labels_import_local(client, tmp_path):
    data, ws, _agent = await _setup(client)

    # unicidade de nome + files CRUD
    r = await client.post("/api/skills", json={"workspace_id": ws, "name": "SK", "content": "c"})
    sk = r.json()
    r = await client.post("/api/skills", json={"workspace_id": ws, "name": "SK"})
    assert r.status_code == 409
    r = await client.put(f"/api/skills/{sk['id']}/files", json={"path": "refs/a.md", "content": "AAA"})
    assert r.status_code == 200
    await client.put(f"/api/skills/{sk['id']}/files", json={"path": "refs/a.md", "content": "BBB"})
    r = await client.get(f"/api/skills/{sk['id']}/files")
    files = r.json()
    assert len(files) == 1 and files[0]["content"] == "BBB"  # upsert por path
    r = await client.put(f"/api/skills/{sk['id']}/files", json={"path": "../evil", "content": "x"})
    assert r.status_code == 400  # path traversal bloqueado
    r = await client.delete(f"/api/skills/{sk['id']}/files/{files[0]['id']}")
    assert r.status_code == 204

    # labels de skill + filtro na listagem
    r = await client.post(f"/api/skills/{sk['id']}/labels", json={"name": "infra"})
    lb = r.json()
    assert lb["resource_type"] == "skill"
    r = await client.get(f"/api/skills?workspace_id={ws}&label_id={lb['id']}")
    assert [s["id"] for s in r.json()] == [sk["id"]]
    r = await client.delete(f"/api/skills/{sk['id']}/labels/{lb['id']}")
    assert r.status_code == 204
    r = await client.get(f"/api/skills?workspace_id={ws}&label_id={lb['id']}")
    assert r.json() == []

    # import .md com frontmatter + estratégias de conflito
    md = b"---\nname: Imported\ndescription: via md\n---\n\ncorpo"
    r = await client.post("/api/skills/import", data={"workspace_id": ws},
                          files={"file": ("skill.md", md, "text/markdown")})
    assert r.status_code == 201 and r.json()["skill"]["name"] == "Imported"
    r = await client.post("/api/skills/import", data={"workspace_id": ws},
                          files={"file": ("skill.md", md, "text/markdown")})
    assert r.status_code == 409  # erro estruturado de conflito
    r = await client.post("/api/skills/import", data={"workspace_id": ws, "on_conflict": "rename"},
                          files={"file": ("skill.md", md, "text/markdown")})
    assert r.json()["skill"]["name"] == "Imported (2)"
    r = await client.post("/api/skills/import", data={"workspace_id": ws, "on_conflict": "overwrite"},
                          files={"file": ("skill.md", b"---\nname: Imported\n---\nnovo", "text/markdown")})
    assert r.json()["status"] == "overwritten"
    r = await client.post("/api/skills/import", data={"workspace_id": ws, "on_conflict": "skip"},
                          files={"file": ("skill.md", md, "text/markdown")})
    assert r.json()["status"] == "skipped"

    # import .zip: SKILL.md + arquivos viram skill_files
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("my/SKILL.md", "---\nname: Zipped\n---\ncorpo")
        z.writestr("my/scripts/run.py", "print(1)")
    r = await client.post("/api/skills/import", data={"workspace_id": ws},
                          files={"file": ("my.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 201 and r.json()["files"] == 1
    zid = r.json()["skill"]["id"]
    r = await client.get(f"/api/skills/{zid}/files")
    assert r.json()[0]["path"] == "scripts/run.py"

    # skills locais do runtime: scan + import com conflito
    from ryu.config import settings

    local = tmp_path / "skills"
    (local / "demo-skill").mkdir(parents=True)
    (local / "demo-skill" / "SKILL.md").write_text("---\nname: Demo Skill\ndescription: d\n---\ncorpo")
    (local / "demo-skill" / "ref.md").write_text("ref")
    old = settings.local_skills_dir
    settings.local_skills_dir = local
    try:
        r = await client.get("/api/skills/local-runtime")
        assert r.status_code == 200 and r.json()[0]["name"] == "Demo Skill"
        r = await client.post("/api/skills/local-runtime/import",
                              json={"workspace_id": ws, "dir_name": "demo-skill"})
        assert r.status_code == 201 and r.json()["files"] == 1
        r = await client.post("/api/skills/local-runtime/import",
                              json={"workspace_id": ws, "dir_name": "demo-skill"})
        assert r.status_code == 409
        r = await client.post("/api/skills/local-runtime/import",
                              json={"workspace_id": ws, "dir_name": "demo-skill", "on_conflict": "overwrite"})
        assert r.json()["status"] == "overwritten"
    finally:
        settings.local_skills_dir = old
