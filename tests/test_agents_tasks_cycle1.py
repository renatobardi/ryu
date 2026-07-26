"""Ciclo 1 — agents-tasks: concorrência por agente, sweeper, archive/restore,
permissão de invocação, tasks por issue (active/runs/rerun), usage por task,
runtime profiles e transcript com seq/type."""
from __future__ import annotations

import asyncio
from datetime import timedelta

from tests.conftest import login


async def _mk_agent(client, ws_id: str, name: str, **extra) -> dict:
    r = await client.post(
        "/api/agents",
        json={"workspace_id": ws_id, "name": name, "handle": name.lower(), "runtime": "echo-fallback", **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _mk_issue_with_task(client, ws_id: str, agent_id: str, title: str) -> tuple[dict, dict]:
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
    issue = r.json()
    r = await client.get("/api/tasks", params={"workspace_id": ws_id, "issue_id": issue["id"]})
    tasks = r.json()
    assert len(tasks) == 1, tasks
    return issue, tasks[0]


async def _drain_runner():
    from ryu.runner import loop as runner_loop

    for _ in range(200):
        if not runner_loop._active:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("runner não drenou")


# ── Concorrência por agente (claim respeita max_concurrent_tasks) ─────
async def test_claim_respects_max_concurrent_tasks(client):
    from ryu.runner.loop import _claim_and_spawn

    data = await login(client, "cycle1-conc@example.com")
    ws_id = data["workspaces"][0]["id"]
    agent = await _mk_agent(client, ws_id, "Conc", max_concurrent_tasks=1)

    i1, t1 = await _mk_issue_with_task(client, ws_id, agent["id"], "task um")
    i2, t2 = await _mk_issue_with_task(client, ws_id, agent["id"], "task dois")

    await _claim_and_spawn()
    # com limite 1, só uma foi claimed (dispatched); a outra segue queued
    r = await client.get("/api/tasks", params={"workspace_id": ws_id, "status": "queued"})
    assert len(r.json()) == 1
    await _drain_runner()
    # segunda rodada pega a que sobrou
    await _claim_and_spawn()
    await _drain_runner()
    r = await client.get("/api/tasks", params={"workspace_id": ws_id, "status": "completed"})
    assert len(r.json()) == 2

    # transcript tem seq crescente e type preenchido
    r = await client.get(f"/api/tasks/{t1['id']}/messages")
    msgs = r.json()
    assert msgs, msgs
    seqs = [m["seq"] for m in msgs]
    assert seqs == sorted(seqs) and seqs[0] >= 1
    assert all(m["type"] for m in msgs)


# ── Sweeper: lease vencido → retry, depois failed; queued TTL ─────────
async def test_sweeper_recovers_orphans(client):
    from sqlalchemy import select

    from ryu.db import SessionLocal
    from ryu.models import Agent, AgentTask, now
    from ryu.runner.loop import _sweep

    data = await login(client, "cycle1-sweep@example.com")
    ws_id = data["workspaces"][0]["id"]
    agent = await _mk_agent(client, ws_id, "Sweep")

    async with SessionLocal() as db:
        task = AgentTask(
            workspace_id=ws_id, agent_id=agent["id"], kind="issue", status="running",
            prompt="órfã", attempt=1, max_attempts=2,
            lease_expires_at=now() - timedelta(minutes=5), started_at=now() - timedelta(hours=1),
        )
        db.add(task)
        ag = await db.get(Agent, agent["id"])
        ag.status = "working"
        await db.commit()
        task_id = task.id

    await _sweep()
    r = await client.get(f"/api/tasks/{task_id}")
    body = r.json()
    assert body["status"] == "queued"  # retry automático
    assert body["attempt"] == 2
    assert body["failure_reason"] == "lease_expired"
    r = await client.get(f"/api/agents/{agent['id']}")
    assert r.json()["status"] == "idle"

    # agora attempt == max_attempts → failed terminal
    async with SessionLocal() as db:
        res = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
        t = res.scalars().first()
        t.status = "running"
        t.lease_expires_at = now() - timedelta(minutes=5)
        await db.commit()
    await _sweep()
    r = await client.get(f"/api/tasks/{task_id}")
    assert r.json()["status"] == "failed"
    assert r.json()["failure_reason"] == "lease_expired"

    # queued TTL
    async with SessionLocal() as db:
        old = AgentTask(workspace_id=ws_id, agent_id=agent["id"], kind="issue", status="queued", prompt="velha")
        db.add(old)
        await db.commit()
        old.created_at = now() - timedelta(hours=48)
        await db.commit()
        old_id = old.id
    await _sweep()
    r = await client.get(f"/api/tasks/{old_id}")
    assert r.json()["status"] == "cancelled"
    assert r.json()["failure_reason"] == "queued_ttl"


# ── Archive / restore / cancel-tasks ──────────────────────────────────
async def test_agent_archive_restore_cancels_tasks(client):
    data = await login(client, "cycle1-arch@example.com")
    ws_id = data["workspaces"][0]["id"]
    agent = await _mk_agent(client, ws_id, "Arch")
    issue, task = await _mk_issue_with_task(client, ws_id, agent["id"], "vai ser cancelada")

    r = await client.post(f"/api/agents/{agent['id']}/archive")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["archived_at"]
    assert task["id"] in body["cancelled_task_ids"]

    r = await client.get(f"/api/tasks/{task['id']}")
    assert r.json()["status"] == "cancelled"

    # some das listagens por default
    r = await client.get("/api/agents", params={"workspace_id": ws_id})
    assert all(a["id"] != agent["id"] for a in r.json())
    r = await client.get("/api/agents", params={"workspace_id": ws_id, "include_archived": "true"})
    assert any(a["id"] == agent["id"] for a in r.json())

    # arquivado não pode ser invocado (assign → 409)
    r = await client.post(
        "/api/issues",
        json={"workspace_id": ws_id, "title": "não deve disparar", "status": "todo",
              "assignee_type": "agent", "assignee_id": agent["id"]},
    )
    assert r.status_code == 409, r.text

    r = await client.post(f"/api/agents/{agent['id']}/restore")
    assert r.status_code == 200
    assert r.json()["archived_at"] is None
    r = await client.get("/api/agents", params={"workspace_id": ws_id})
    assert any(a["id"] == agent["id"] for a in r.json())

    # cancel-tasks explícito
    _, t2 = await _mk_issue_with_task(client, ws_id, agent["id"], "cancela em lote")
    r = await client.post(f"/api/agents/{agent['id']}/cancel-tasks")
    assert r.status_code == 200
    assert t2["id"] in r.json()["cancelled_task_ids"]


# ── Permissão de invocação + gerenciamento ────────────────────────────
async def test_invocation_permission(client):
    from ryu.db import SessionLocal
    from ryu.models import Member

    data_a = await login(client, "cycle1-owner@example.com")
    ws_id = data_a["workspaces"][0]["id"]
    agent = await _mk_agent(client, ws_id, "Priv", permission_mode="private")
    issue, _ = await _mk_issue_with_task(client, ws_id, agent["id"], "dono pode")  # dono invoca

    data_b = await login(client, "cycle1-other@example.com")  # troca o cookie p/ user B
    user_b = data_b["user"]["id"]
    async with SessionLocal() as db:
        db.add(Member(workspace_id=ws_id, user_id=user_b, role="member"))
        await db.commit()

    # B não gerencia agente de A
    r = await client.patch(f"/api/agents/{agent['id']}", json={"description": "hack"})
    assert r.status_code == 403
    r = await client.post(f"/api/agents/{agent['id']}/archive")
    assert r.status_code == 403

    # B não invoca agente private de A
    r = await client.post(
        "/api/issues",
        json={"workspace_id": ws_id, "title": "sem permissão", "status": "todo",
              "assignee_type": "agent", "assignee_id": agent["id"]},
    )
    assert r.status_code == 403, r.text
    r = await client.post("/api/chat/sessions", json={"workspace_id": ws_id, "agent_id": agent["id"]})
    assert r.status_code == 403, r.text

    # A libera via public_to + allow-list com B
    data_a = await login(client, "cycle1-owner@example.com")
    r = await client.patch(f"/api/agents/{agent['id']}", json={"permission_mode": "public_to"})
    assert r.status_code == 200
    r = await client.put(
        f"/api/agents/{agent['id']}/invocation-targets",
        json={"targets": [{"target_type": "member", "target_id": user_b}]},
    )
    assert r.status_code == 200

    await login(client, "cycle1-other@example.com")
    r = await client.post(
        "/api/issues",
        json={"workspace_id": ws_id, "title": "agora pode", "status": "todo",
              "assignee_type": "agent", "assignee_id": agent["id"]},
    )
    assert r.status_code == 201, r.text


# ── Tasks por issue: active / runs / rerun ────────────────────────────
async def test_issue_active_runs_rerun(client):
    from ryu.runner.loop import _run_one

    data = await login(client, "cycle1-rerun@example.com")
    ws_id = data["workspaces"][0]["id"]
    agent = await _mk_agent(client, ws_id, "Rerun")
    issue, task = await _mk_issue_with_task(client, ws_id, agent["id"], "primeira run")

    r = await client.get(f"/api/tasks/issues/{issue['id']}/active")
    assert r.json()["task"]["id"] == task["id"]

    # rerun com task ativa → 409
    r = await client.post(f"/api/tasks/issues/{issue['id']}/rerun")
    assert r.status_code == 409

    await _run_one(task["id"])
    r = await client.get(f"/api/tasks/issues/{issue['id']}/active")
    assert r.json()["task"] is None

    r = await client.post(f"/api/tasks/issues/{issue['id']}/rerun")
    assert r.status_code == 201, r.text
    rerun = r.json()
    assert rerun["rerun_of_task_id"] == task["id"]

    r = await client.get(f"/api/tasks/issues/{issue['id']}/runs")
    ids = [t["id"] for t in r.json()]
    assert set(ids) == {task["id"], rerun["id"]}

    # filtro issue_id no list geral
    r = await client.get("/api/tasks", params={"workspace_id": ws_id, "issue_id": issue["id"]})
    assert len(r.json()) == 2


# ── Usage por task ────────────────────────────────────────────────────
async def test_task_usage_report_and_summary(client):
    data = await login(client, "cycle1-usage@example.com")
    ws_id = data["workspaces"][0]["id"]
    agent = await _mk_agent(client, ws_id, "Usage")
    issue, task = await _mk_issue_with_task(client, ws_id, agent["id"], "usage")

    r = await client.post(
        f"/api/tasks/{task['id']}/usage",
        json={"provider": "anthropic", "model": "claude-sonnet-4-5", "input_tokens": 1000,
              "output_tokens": 250, "cache_read_tokens": 400, "cost_usd": 0.0123},
    )
    assert r.status_code == 201, r.text

    r = await client.get(f"/api/tasks/{task['id']}/usage")
    rows = r.json()
    assert len(rows) == 1 and rows[0]["input_tokens"] == 1000

    r = await client.get(f"/api/tasks/{task['id']}")
    body = r.json()
    assert body["input_tokens"] == 1000 and body["output_tokens"] == 250
    assert abs(body["cost_usd"] - 0.0123) < 1e-9

    r = await client.get("/api/tasks/usage/summary", params={"workspace_id": ws_id})
    summary = r.json()
    assert summary["totals"]["input_tokens"] == 1000
    assert any(m["model"] == "anthropic/claude-sonnet-4-5" for m in summary["by_model"])
    assert any(a["agent_id"] == agent["id"] for a in summary["by_agent"])


# ── Runtime profiles ──────────────────────────────────────────────────
async def test_runtime_profiles_crud_and_agent_link(client):
    data = await login(client, "cycle1-prof@example.com")
    ws_id = data["workspaces"][0]["id"]

    r = await client.post(
        "/api/runtime-profiles",
        json={"workspace_id": ws_id, "display_name": "Claude custom", "protocol_family": "claude",
              "command_name": "claude", "fixed_args": ["--dangerously-skip-permissions"]},
    )
    assert r.status_code == 201, r.text
    profile = r.json()

    r = await client.get("/api/runtime-profiles", params={"workspace_id": ws_id})
    assert any(p["id"] == profile["id"] for p in r.json())

    # protocol_family limitado
    r = await client.post(
        "/api/runtime-profiles",
        json={"workspace_id": ws_id, "display_name": "x", "protocol_family": "nope", "command_name": "x"},
    )
    assert r.status_code == 422

    agent = await _mk_agent(client, ws_id, "Prof", profile_id=profile["id"])
    assert agent["profile_id"] == profile["id"]

    # em uso → não deleta
    r = await client.delete(f"/api/runtime-profiles/{profile['id']}")
    assert r.status_code == 409

    r = await client.patch(f"/api/agents/{agent['id']}", json={"profile_id": None})
    assert r.status_code == 200
    r = await client.delete(f"/api/runtime-profiles/{profile['id']}")
    assert r.status_code == 204


# ── Cancel: pedido + guarda de status (fila) ──────────────────────────
async def test_cancel_queued_task_and_workdir_columns(client):
    data = await login(client, "cycle1-cancel@example.com")
    ws_id = data["workspaces"][0]["id"]
    agent = await _mk_agent(client, ws_id, "Cancel")
    issue, task = await _mk_issue_with_task(client, ws_id, agent["id"], "cancelar")

    r = await client.post(f"/api/tasks/{task['id']}/cancel")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "cancelled"
    assert body["cancel_requested"] is True

    # runner não executa task cancelada
    from ryu.runner.loop import _run_one

    await _run_one(task["id"])
    r = await client.get(f"/api/tasks/{task['id']}")
    assert r.json()["status"] == "cancelled"
