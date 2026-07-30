"""Testes do domínio daemon-cli (ciclo 1).

Cobre: register/heartbeat/deregister, tokens rdt_ (escopo/expiração),
claim/lease/report do protocolo de execução externa, recover-orphans,
update remoto + model-list (initiate → pending no heartbeat → report → poll),
comentários paginados thread-aware, by-key, usage agregado da issue e o
config local do CLI.
"""
from __future__ import annotations

import pytest

from tests.conftest import login


async def _setup_workspace(client, email: str = "daemon@ryu.dev") -> tuple[dict, str]:
    data = await login(client, email)
    ws = data["workspaces"][0]
    return data["user"], ws


async def _create_agent(client, ws_id: str, runtime: str = "claude") -> dict:
    r = await client.post(
        "/api/agents",
        json={"workspace_id": ws_id, "name": f"Bot {runtime}", "handle": f"bot-{runtime}", "runtime": runtime},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _register_daemon(client, ws_id: str, daemon_id: str = "test-host", providers=("claude",)) -> dict:
    r = await client.post(
        "/api/daemon/register",
        json={
            "workspace_id": ws_id,
            "daemon_id": daemon_id,
            "device_name": "Test Machine",
            "runtimes": [{"provider": p, "version": "1.0.0"} for p in providers],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _enqueue_issue_task(client, ws_id: str, agent_id: str, title="Task p/ daemon") -> dict:
    r = await client.post(
        "/api/issues",
        json={
            "workspace_id": ws_id,
            "title": title,
            "status": "todo",
            "assignee_type": "agent",
            "assignee_id": agent_id,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# ── Register / heartbeat / tokens ─────────────────────────────────────
async def test_daemon_register_heartbeat_and_token_scope(client):
    _user, ws = await _setup_workspace(client)
    data = await _register_daemon(client, ws["id"])
    assert data["daemon_token"] and data["daemon_token"].startswith("rdt_")
    assert len(data["runtimes"]) == 1
    rt = data["runtimes"][0]
    assert rt["provider"] == "claude"
    assert rt["status"] == "online"

    rdt = data["daemon_token"]
    # watch list com rdt_: só o workspace do escopo
    r = await client.get("/api/daemon/workspaces", headers=_bearer(rdt))
    assert r.status_code == 200
    assert [w["id"] for w in r.json()] == [ws["id"]]

    # heartbeat com o rdt_ → ack ok
    r = await client.post("/api/daemon/heartbeat", json={"runtime_id": rt["id"]}, headers=_bearer(rdt))
    assert r.status_code == 200
    ack = r.json()
    assert ack["status"] == "ok"
    assert ack["runtime_id"] == rt["id"]

    # heartbeat de runtime removido → runtime_gone (daemon deve re-registrar)
    r = await client.post("/api/daemon/heartbeat", json={"runtime_id": "nope"}, headers=_bearer(rdt))
    assert r.status_code == 200
    assert r.json()["runtime_gone"] is True

    # rdt_ NÃO dá acesso a outro workspace
    data2 = await login(client, "other-owner@ryu.dev")
    ws2 = data2["workspaces"][0]
    r = await client.post(
        "/api/daemon/register",
        json={"workspace_id": ws2["id"], "daemon_id": "x", "runtimes": [{"provider": "claude"}]},
        headers=_bearer(rdt),
    )
    assert r.status_code == 403

    # deregister derruba p/ offline
    await login(client, "daemon@ryu.dev")
    r = await client.post(
        "/api/daemon/deregister",
        json={"workspace_id": ws["id"], "daemon_id": "test-host"},
        headers=_bearer(rdt),
    )
    assert r.status_code == 200
    r = await client.get("/api/runtimes", params={"workspace_id": ws["id"]})
    assert r.status_code == 200
    assert r.json()[0]["status"] == "offline"


async def test_daemon_token_issue_list_revoke(client):
    _user, ws = await _setup_workspace(client, "tok@ryu.dev")
    r = await client.post("/api/daemon/token", json={"workspace_id": ws["id"], "daemon_id": "cli-1"})
    assert r.status_code == 201, r.text
    tok = r.json()
    assert tok["token"].startswith("rdt_")
    assert tok["expires_at"] is not None

    r = await client.get("/api/daemon/tokens", params={"workspace_id": ws["id"]})
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()]
    assert tok["id"] in ids

    # token funciona
    r = await client.get("/api/daemon/workspaces", headers=_bearer(tok["token"]))
    assert r.status_code == 200

    # revoga → deixa de funcionar
    r = await client.delete(f"/api/daemon/tokens/{tok['id']}", params={"workspace_id": ws["id"]})
    assert r.status_code == 200
    r = await client.get("/api/daemon/workspaces", headers=_bearer(tok["token"]))
    assert r.status_code == 401


# ── Protocolo de execução: claim → start → messages → complete ────────
async def test_daemon_claim_execute_complete_cycle(client):
    _user, ws = await _setup_workspace(client, "exec@ryu.dev")
    agent = await _create_agent(client, ws["id"])
    reg = await _register_daemon(client, ws["id"], daemon_id="exec-host")
    rdt = reg["daemon_token"]
    rt = reg["runtimes"][0]

    issue = await _enqueue_issue_task(client, ws["id"], agent["id"])

    # claim atômico: queued → dispatched com lease + payload de execução
    r = await client.post(
        "/api/daemon/tasks/claim",
        json={"runtime_ids": [rt["id"]], "max_tasks": 5},
        headers=_bearer(rdt),
    )
    assert r.status_code == 200, r.text
    tasks = r.json()["tasks"]
    assert len(tasks) == 1
    task = tasks[0]
    assert task["status"] == "dispatched"
    assert task["lease_expires_at"] is not None
    assert task["agent"]["runtime"] == "claude"
    assert task["prompt"]

    # segundo claim não duplica
    r = await client.post(
        "/api/daemon/tasks/claim", json={"runtime_id": rt["id"]}, headers=_bearer(rdt)
    )
    assert r.json()["tasks"] == []

    # start: dispatched → running
    r = await client.post(f"/api/daemon/tasks/{task['id']}/start", headers=_bearer(rdt))
    assert r.status_code == 200 and r.json()["ok"]

    # progress renova lease e devolve cancel_requested
    r = await client.post(f"/api/daemon/tasks/{task['id']}/progress", json={"message": "rodando"}, headers=_bearer(rdt))
    assert r.status_code == 200
    assert r.json()["cancel_requested"] is False

    # messages em lote com seq contínuo
    r = await client.post(
        f"/api/daemon/tasks/{task['id']}/messages",
        json={"messages": [
            {"role": "stdout", "content": "linha 1"},
            {"role": "assistant", "type": "assistant", "content": "pensando..."},
        ]},
        headers=_bearer(rdt),
    )
    assert r.status_code == 201
    assert r.json()["added"] == 2

    # usage (tokens)
    r = await client.post(
        f"/api/daemon/tasks/{task['id']}/usage",
        json={"provider": "anthropic", "model": "sonnet", "input_tokens": 100, "output_tokens": 50},
        headers=_bearer(rdt),
    )
    assert r.status_code == 201

    # complete com result_summary
    r = await client.post(
        f"/api/daemon/tasks/{task['id']}/complete",
        json={"result_summary": "feito pelo daemon", "session_id": "sess-1"},
        headers=_bearer(rdt),
    )
    assert r.status_code == 200 and r.json()["ok"]

    r = await client.get(f"/api/tasks/{task['id']}")
    t = r.json()
    assert t["status"] == "completed"
    assert t["result_summary"] == "feito pelo daemon"
    assert t["session_id"] == "sess-1"

    # efeito colateral: comentário na issue + in_review
    r = await client.get(f"/api/issues/{issue['id']}")
    assert r.json()["status"] == "in_review"
    r = await client.get(f"/api/issues/{issue['id']}/comments")
    bodies = [c["body"] for c in r.json()]
    assert any("feito pelo daemon" in b for b in bodies)

    # usage agregado da issue
    r = await client.get(f"/api/issues/{issue['id']}/usage")
    assert r.status_code == 200
    agg = r.json()
    assert agg["input_tokens"] == 100 and agg["output_tokens"] == 50
    assert agg["task_count"] == 1


async def test_daemon_fail_retry_and_cancel_ack(client):
    _user, ws = await _setup_workspace(client, "fail@ryu.dev")
    agent = await _create_agent(client, ws["id"])
    reg = await _register_daemon(client, ws["id"], daemon_id="fail-host")
    rdt = reg["daemon_token"]
    rt = reg["runtimes"][0]

    await _enqueue_issue_task(client, ws["id"], agent["id"], "vai falhar")
    r = await client.post("/api/daemon/tasks/claim", json={"runtime_id": rt["id"]}, headers=_bearer(rdt))
    task = r.json()["tasks"][0]
    await client.post(f"/api/daemon/tasks/{task['id']}/start", headers=_bearer(rdt))

    # fail com razão retryable → volta p/ queued com attempt+1
    r = await client.post(
        f"/api/daemon/tasks/{task['id']}/fail",
        json={"error": "processo morreu", "failure_reason": "crash"},
        headers=_bearer(rdt),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    r = await client.get(f"/api/tasks/{task['id']}")
    assert r.json()["attempt"] == 2

    # re-claim e cancelamento: user cancela → daemon vê cancel e acka
    r = await client.post("/api/daemon/tasks/claim", json={"runtime_id": rt["id"]}, headers=_bearer(rdt))
    task = r.json()["tasks"][0]
    await client.post(f"/api/daemon/tasks/{task['id']}/start", headers=_bearer(rdt))
    r = await client.post(f"/api/tasks/{task['id']}/cancel")
    assert r.status_code == 200
    r = await client.get(f"/api/daemon/tasks/{task['id']}/status", headers=_bearer(rdt))
    assert r.json()["cancel_requested"] is True
    r = await client.post(f"/api/daemon/tasks/{task['id']}/cancel-ack", headers=_bearer(rdt))
    assert r.status_code == 200
    r = await client.get(f"/api/tasks/{task['id']}")
    assert r.json()["status"] == "cancelled"


async def test_daemon_recover_orphans(client):
    _user, ws = await _setup_workspace(client, "orphan@ryu.dev")
    agent = await _create_agent(client, ws["id"])
    reg = await _register_daemon(client, ws["id"], daemon_id="orphan-host")
    rdt = reg["daemon_token"]
    rt = reg["runtimes"][0]

    await _enqueue_issue_task(client, ws["id"], agent["id"], "órfã")
    r = await client.post("/api/daemon/tasks/claim", json={"runtime_id": rt["id"]}, headers=_bearer(rdt))
    task = r.json()["tasks"][0]
    await client.post(f"/api/daemon/tasks/{task['id']}/start", headers=_bearer(rdt))

    # daemon reiniciou: recover-orphans devolve a task p/ a fila
    r = await client.post(f"/api/daemon/runtimes/{rt['id']}/recover-orphans", headers=_bearer(rdt))
    assert r.status_code == 200
    rec = r.json()["recovered"]
    assert rec and rec[0]["task_id"] == task["id"] and rec[0]["status"] == "queued"
    r = await client.get(f"/api/tasks/{task['id']}")
    assert r.json()["status"] == "queued"


# ── Update remoto + model-list (initiate → heartbeat → report → poll) ─
async def test_remote_update_cycle(client):
    _user, ws = await _setup_workspace(client, "upd@ryu.dev")
    reg = await _register_daemon(client, ws["id"], daemon_id="upd-host")
    rdt = reg["daemon_token"]
    rt = reg["runtimes"][0]

    # UI pede update
    r = await client.post(f"/api/runtimes/{rt['id']}/update", json={"target_version": "latest"})
    assert r.status_code == 202, r.text
    upd = r.json()
    assert upd["status"] == "pending"

    # entregue no heartbeat-ack
    r = await client.post("/api/daemon/heartbeat", json={"runtime_id": rt["id"]}, headers=_bearer(rdt))
    ack = r.json()
    assert ack["pending_update"]["id"] == upd["id"]

    # segundo heartbeat não re-entrega
    r = await client.post("/api/daemon/heartbeat", json={"runtime_id": rt["id"]}, headers=_bearer(rdt))
    assert "pending_update" not in r.json()

    # daemon reporta resultado
    r = await client.post(
        f"/api/daemon/runtimes/{rt['id']}/update/{upd['id']}/result",
        json={"status": "completed", "message": "ok", "version": "2.0.0"},
        headers=_bearer(rdt),
    )
    assert r.status_code == 200

    # cliente faz polling
    r = await client.get(f"/api/runtimes/{rt['id']}/update/{upd['id']}")
    assert r.status_code == 200
    assert r.json()["status"] == "completed"
    assert r.json()["version"] == "2.0.0"


async def test_model_list_cycle(client):
    _user, ws = await _setup_workspace(client, "mdl@ryu.dev")
    reg = await _register_daemon(client, ws["id"], daemon_id="mdl-host")
    rdt = reg["daemon_token"]
    rt = reg["runtimes"][0]

    r = await client.post(f"/api/runtimes/{rt['id']}/models")
    assert r.status_code == 202
    req = r.json()

    r = await client.post("/api/daemon/heartbeat", json={"runtime_id": rt["id"]}, headers=_bearer(rdt))
    assert r.json()["pending_model_list"]["id"] == req["id"]

    r = await client.post(
        f"/api/daemon/runtimes/{rt['id']}/models/{req['id']}/result",
        json={"models": ["opus", "sonnet", "haiku"]},
        headers=_bearer(rdt),
    )
    assert r.status_code == 200

    r = await client.get(f"/api/runtimes/{rt['id']}/models/{req['id']}")
    assert r.status_code == 200
    assert r.json()["models"] == ["opus", "sonnet", "haiku"]


# ── CLI token handoff + members ───────────────────────────────────────
async def test_cli_token_and_members(client):
    _user, ws = await _setup_workspace(client, "cli@ryu.dev")
    r = await client.post("/api/cli-token")
    assert r.status_code == 200
    token = r.json()["token"]
    assert token.startswith("ryu_")
    # o token emitido funciona como Bearer
    r = await client.get("/api/auth/me", headers=_bearer(token))
    assert r.status_code == 200
    assert r.json()["email"] == "cli@ryu.dev"

    r = await client.get(f"/api/workspaces/{ws['id']}/members")
    assert r.status_code == 200
    members = r.json()
    assert len(members) == 1 and members[0]["email"] == "cli@ryu.dev"

    r = await client.get(f"/api/workspaces/{ws['slug']}")
    assert r.status_code == 200
    assert r.json()["id"] == ws["id"]

    # página do fluxo de login do CLI
    r = await client.get("/cli-login", params={"redirect_uri": "http://127.0.0.1:1234/callback"})
    assert r.status_code == 200
    r = await client.get("/cli-login", params={"redirect_uri": "https://evil.example.com/x"})
    assert r.status_code == 400


# ── by-key ────────────────────────────────────────────────────────────
async def test_issue_by_key(client):
    _user, ws = await _setup_workspace(client, "bykey@ryu.dev")
    r = await client.post("/api/issues", json={"workspace_id": ws["id"], "title": "Via key"})
    issue = r.json()
    r = await client.get(f"/api/issues/by-key/{issue['key']}", params={"workspace_id": ws["id"]})
    assert r.status_code == 200
    assert r.json()["id"] == issue["id"]
    r = await client.get("/api/issues/by-key/RYU-99999", params={"workspace_id": ws["id"]})
    assert r.status_code == 404


# ── Comentários paginados (thread/recent/cursor/since) ────────────────
async def test_comments_thread_pagination(client):
    _user, ws = await _setup_workspace(client, "cmt@ryu.dev")
    r = await client.post("/api/issues", json={"workspace_id": ws["id"], "title": "Thread test"})
    issue = r.json()

    r = await client.post(f"/api/issues/{issue['id']}/comments", json={"body": "raiz"})
    root = r.json()
    replies = []
    for i in range(5):
        r = await client.post(
            f"/api/issues/{issue['id']}/comments",
            json={"body": f"reply {i}", "parent_comment_id": root["id"]},
        )
        replies.append(r.json())

    # thread completo: raiz + 5 réplicas, sem cursor
    r = await client.get(f"/api/issues/{issue['id']}/comments", params={"thread": root["id"]})
    assert r.status_code == 200
    assert len(r.json()) == 6
    assert "X-Ryu-Next-Before" not in r.headers

    # tail=2: raiz + 2 mais recentes, com cursor (há réplicas mais antigas)
    r = await client.get(
        f"/api/issues/{issue['id']}/comments", params={"thread": root["id"], "tail": 2}
    )
    page = r.json()
    assert [c["body"] for c in page] == ["raiz", "reply 3", "reply 4"]
    assert "X-Ryu-Next-Before" in r.headers
    before = r.headers["X-Ryu-Next-Before"]
    before_id = r.headers["X-Ryu-Next-Before-Id"]

    # página seguinte via cursor
    r = await client.get(
        f"/api/issues/{issue['id']}/comments",
        params={"thread": root["id"], "tail": 2, "before": before, "before_id": before_id},
    )
    page2 = r.json()
    assert [c["body"] for c in page2] == ["raiz", "reply 1", "reply 2"]

    # âncora numa réplica sobe até a raiz
    r = await client.get(f"/api/issues/{issue['id']}/comments", params={"thread": replies[2]["id"]})
    assert r.json()[0]["body"] == "raiz"

    # tail exato (=5) não emite cursor (página de borda)
    r = await client.get(
        f"/api/issues/{issue['id']}/comments", params={"thread": root["id"], "tail": 5}
    )
    assert len(r.json()) == 6
    assert "X-Ryu-Next-Before" not in r.headers

    # cursor sem modo → 400
    r = await client.get(
        f"/api/issues/{issue['id']}/comments", params={"before": before, "before_id": before_id}
    )
    assert r.status_code == 400


async def test_comments_recent_mode(client):
    _user, ws = await _setup_workspace(client, "recent@ryu.dev")
    r = await client.post("/api/issues", json={"workspace_id": ws["id"], "title": "Recent test"})
    issue = r.json()

    roots = []
    for i in range(3):
        r = await client.post(f"/api/issues/{issue['id']}/comments", json={"body": f"thread {i}"})
        roots.append(r.json())
    # réplica na thread 0 → vira a mais ativa
    await client.post(
        f"/api/issues/{issue['id']}/comments",
        json={"body": "res 0", "parent_comment_id": roots[0]["id"]},
    )

    r = await client.get(f"/api/issues/{issue['id']}/comments", params={"recent": 2})
    assert r.status_code == 200
    bodies = [c["body"] for c in r.json()]
    # 2 threads mais ativas (thread 2 e thread 0), oldest-active primeiro
    assert bodies == ["thread 2", "thread 0", "res 0"]
    # há thread mais antiga → cursor de thread emitido
    assert "X-Ryu-Next-Before" in r.headers

    r = await client.get(
        f"/api/issues/{issue['id']}/comments",
        params={
            "recent": 2,
            "before": r.headers["X-Ryu-Next-Before"],
            "before_id": r.headers["X-Ryu-Next-Before-Id"],
        },
    )
    assert [c["body"] for c in r.json()] == ["thread 1"]
    assert "X-Ryu-Next-Before" not in r.headers


# ── Config local do CLI ───────────────────────────────────────────────
def test_cliconf_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("RYU_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("RYU_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("RYU_TOKEN", raising=False)
    monkeypatch.delenv("RYU_URL", raising=False)
    from ryu import cliconf

    assert cliconf.load_config() == {}
    cliconf.set_value("server_url", "http://example.com:9000")
    cliconf.set_value("workspace_id", "ws-123")
    cliconf.set_value("token", "ryu_abc")
    assert cliconf.resolve_server_url() == "http://example.com:9000"
    assert cliconf.resolve_workspace_id(None) == "ws-123"
    assert cliconf.resolve_workspace_id("flag-wins") == "flag-wins"
    monkeypatch.setenv("RYU_WORKSPACE_ID", "env-wins")
    assert cliconf.resolve_workspace_id(None) == "env-wins"
    assert cliconf.resolve_token() == "ryu_abc"
    with pytest.raises(ValueError):
        cliconf.set_value("nope", "x")


def test_adapters_detection_and_overrides(monkeypatch, tmp_path):
    from ryu.runner import adapters

    # override de PATH aponta p/ binário fake
    fake = tmp_path / "claude"
    fake.write_text("#!/bin/sh\necho ok\n")
    fake.chmod(0o755)
    monkeypatch.setenv("RYU_CLAUDE_PATH", str(fake))
    monkeypatch.setenv("RYU_CLAUDE_MODEL", "opus")
    monkeypatch.setenv("RYU_CLAUDE_ARGS", '--sandbox "read only"')

    ov = adapters.agent_env_overrides("claude")
    assert ov["path"] == str(fake)
    assert ov["model"] == "opus"
    assert ov["args"] == ["--sandbox", "read only"]  # shellword parsing

    detected = {d["provider"]: d for d in adapters.detect_runtimes()}
    assert set(detected) == {"claude", "devin", "agy", "opencode"}
    assert detected["claude"]["available"] is True
    assert detected["claude"]["path"] == str(fake)

    argv = adapters.build_command("claude", "faz algo", {})
    assert argv is not None
    assert argv[0] == str(fake)
    assert "--model" in argv and "opus" in argv
    assert argv[-2:] == ["--sandbox", "read only"]
