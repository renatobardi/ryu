"""Fluxo completo: workspace → label → issue → comment → move →
agent 'echo-fallback' → atribuição cria AgentTask → runner completa (tick
manual) → comentário do agente + issue em in_review → inbox → usage."""
from __future__ import annotations

from tests.conftest import login


async def _tick_runner_until_done(client, workspace_id: str, task_id: str) -> dict:
    """Executa o tick do runner manualmente (lifespan não roda sob ASGITransport)."""
    from ryu.runner.loop import _run_one

    await _run_one(task_id)
    r = await client.get(f"/api/tasks/{task_id}")
    assert r.status_code == 200, r.text
    return r.json()


async def test_full_flow(client):
    data = await login(client, "flow-user@example.com")
    user_id = data["user"]["id"]
    ws = data["workspaces"][0]
    ws_id = ws["id"]

    # ── label ─────────────────────────────────────────────────────────
    r = await client.post(
        "/api/issues/labels",
        json={"workspace_id": ws_id, "name": "bug", "color": "#ef4444"},
    )
    assert r.status_code == 201, r.text
    label = r.json()
    assert label["name"] == "bug"

    r = await client.get("/api/issues/labels", params={"workspace_id": ws_id})
    assert r.status_code == 200
    assert any(lb["id"] == label["id"] for lb in r.json())

    # ── issue ─────────────────────────────────────────────────────────
    r = await client.post(
        "/api/issues",
        json={
            "workspace_id": ws_id,
            "title": "Corrigir crash no board",
            "description": "Stacktrace ao arrastar card.",
            "status": "backlog",
            "priority": "high",
            "label_ids": [label["id"]],
        },
    )
    assert r.status_code == 201, r.text
    issue = r.json()
    assert issue["key"].split("-")[1].isdigit()
    assert issue["status"] == "backlog"
    assert [lb["id"] for lb in issue["labels"]] == [label["id"]]

    # ── comment ───────────────────────────────────────────────────────
    r = await client.post(
        f"/api/issues/{issue['id']}/comments", json={"body": "Reproduzi localmente."}
    )
    assert r.status_code == 201, r.text
    r = await client.get(f"/api/issues/{issue['id']}/comments")
    assert r.status_code == 200
    assert len(r.json()) == 1

    # ── move de status (backlog → todo) ───────────────────────────────
    r = await client.post(f"/api/issues/{issue['id']}/move", json={"status": "todo"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "todo"

    # sem agente atribuído ainda → nenhuma task
    r = await client.get("/api/tasks", params={"workspace_id": ws_id})
    assert r.status_code == 200
    assert r.json() == []

    # ── agent runtime echo-fallback ───────────────────────────────────
    r = await client.post(
        "/api/agents",
        json={
            "workspace_id": ws_id,
            "name": "Echo",
            "handle": "echo",
            "runtime": "echo-fallback",
        },
    )
    assert r.status_code == 201, r.text
    agent = r.json()
    assert agent["runtime"] == "echo-fallback"
    assert agent["status"] == "idle"

    # ── atribuir issue ao agente → AgentTask queued ───────────────────
    r = await client.patch(
        f"/api/issues/{issue['id']}",
        json={"assignee_type": "agent", "assignee_id": agent["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["assignee_id"] == agent["id"]

    r = await client.get("/api/tasks", params={"workspace_id": ws_id, "status": "queued"})
    assert r.status_code == 200
    tasks = r.json()
    assert len(tasks) == 1, f"esperava 1 AgentTask queued, veio {tasks}"
    task = tasks[0]
    assert task["agent_id"] == agent["id"]
    assert task["issue_id"] == issue["id"]
    assert task["kind"] == "issue"
    assert "Corrigir crash no board" in task["prompt"]

    # re-atribuir não duplica task ativa
    r = await client.patch(f"/api/issues/{issue['id']}", json={"status": "in_progress"})
    assert r.status_code == 200
    r = await client.get("/api/tasks", params={"workspace_id": ws_id})
    assert len(r.json()) == 1

    # ── runner completa em modo fallback (tick manual) ────────────────
    done = await _tick_runner_until_done(client, ws_id, task["id"])
    assert done["status"] == "completed", done
    assert done["result_summary"]
    assert done["finished_at"]

    # mensagens da task registradas
    r = await client.get(f"/api/tasks/{task['id']}/messages")
    assert r.status_code == 200
    roles = [m["role"] for m in r.json()]
    assert "system" in roles

    # agente comentou na issue e ela foi para in_review
    r = await client.get(f"/api/issues/{issue['id']}")
    assert r.status_code == 200
    detail = r.json()
    assert detail["status"] == "in_review"
    r = await client.get(f"/api/issues/{issue['id']}/comments")
    bodies = r.json()
    agent_comments = [c for c in bodies if c["author_type"] == "agent"]
    assert agent_comments, bodies
    assert agent_comments[0]["author_id"] == agent["id"]

    # agente voltou a idle
    r = await client.get(f"/api/agents/{agent['id']}")
    assert r.json()["status"] == "idle"

    # ── inbox recebeu notificação para o criador ──────────────────────
    r = await client.get("/api/inbox", params={"workspace_id": ws_id})
    assert r.status_code == 200
    items = r.json()
    assert items, "inbox deveria ter item após task completada"
    item = items[0]
    assert item["user_id"] == user_id
    assert item["issue_id"] == issue["id"]
    assert issue["key"] in item["title"]

    r = await client.get("/api/inbox/unread-count", params={"workspace_id": ws_id})
    assert r.json()["unread"] >= 1

    r = await client.post("/api/inbox/mark-all-read", params={"workspace_id": ws_id})
    assert r.status_code == 200
    r = await client.get("/api/inbox/unread-count", params={"workspace_id": ws_id})
    assert r.json()["unread"] == 0

    # ── usage responde e agrega a task ────────────────────────────────
    r = await client.get("/api/usage/summary", params={"workspace_id": ws_id})
    assert r.status_code == 200, r.text
    usage = r.json()
    assert usage["workspace_id"] == ws_id
    assert usage["totals"]["tasks"] >= 1
    assert usage["totals"]["by_status"].get("completed", 0) >= 1
    assert any(a["agent_id"] == agent["id"] for a in usage["by_agent"])

    # ── activity log da issue registrou o essencial ───────────────────
    r = await client.get(f"/api/issues/{issue['id']}/activity")
    actions = {a["action"] for a in r.json()}
    assert {"created", "commented", "status_changed"} <= actions
    assert "task_queued" in actions
