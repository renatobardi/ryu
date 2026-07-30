"""Ciclo 1 — chat-squads: pending-task/cancel/draft-restore, unread/read,
sessão arquivada somente leitura, pinned agents, título sanitizado, squads
(assignee_type='squad', loop de delegação por comentário, evaluation do líder,
papéis + status de membros, briefing persistente)."""
from __future__ import annotations

from tests.conftest import login


async def _mk_agent(client, ws_id: str, name: str, **extra) -> dict:
    r = await client.post(
        "/api/agents",
        json={"workspace_id": ws_id, "name": name, "handle": name.lower(), "runtime": "claude", **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _mk_session(client, ws_id: str, agent_id: str) -> dict:
    r = await client.post("/api/chat/sessions", json={"workspace_id": ws_id, "agent_id": agent_id})
    assert r.status_code == 200, r.text
    return r.json()


async def _run_task(client, ws_id: str, task_id: str):
    from tests.conftest import run_task_through_daemon

    await run_task_through_daemon(client, ws_id, task_id=task_id)


# ── chat: pending-task + cancel + draft restore ───────────────────────
async def test_chat_pending_task_cancel_and_draft_restore(client):
    data = await login(client, "cs-cancel@example.com")
    ws_id = data["workspaces"][0]["id"]
    agent = await _mk_agent(client, ws_id, "Canceler")
    session = await _mk_session(client, ws_id, agent["id"])

    r = await client.post(f"/api/chat/{session['id']}/messages", json={"content": "faz um resumo aí"})
    assert r.status_code == 201, r.text
    task_id = r.json()["task_id"]

    # pending-task da sessão
    r = await client.get(f"/api/chat/{session['id']}/pending-task")
    assert r.status_code == 200
    assert r.json()["task"]["id"] == task_id
    assert r.json()["task"]["status"] in ("queued", "dispatched", "running")

    # agregados por usuário/workspace
    r = await client.get("/api/chat/pending-tasks", params={"workspace_id": ws_id})
    assert any(t["id"] == task_id for t in r.json())
    r = await client.get("/api/chat/pending-tasks/has-any", params={"workspace_id": ws_id})
    assert r.json()["has_any"] is True

    # stop: cancela sem resposta produzida → draft restore + user msg removida
    r = await client.post(f"/api/chat/{session['id']}/cancel")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "cancelled"
    assert body["restore"] is not None
    assert body["restore"]["content"] == "faz um resumo aí"

    r = await client.get(f"/api/chat/{session['id']}/messages")
    assert r.json() == []  # mensagem do usuário voltou pro composer

    # GET lista o restore; DELETE consome (idempotente)
    r = await client.get(f"/api/chat/{session['id']}/draft-restores")
    restores = r.json()
    assert len(restores) == 1 and restores[0]["task_id"] == task_id
    rid = restores[0]["id"]
    r = await client.delete(f"/api/chat/{session['id']}/draft-restores/{rid}")
    assert r.json()["restore"]["content"] == "faz um resumo aí"
    r = await client.delete(f"/api/chat/{session['id']}/draft-restores/{rid}")
    assert r.status_code == 200 and r.json()["restore"] is None  # idempotente

    # sem task pendente → 404 no stop
    r = await client.post(f"/api/chat/{session['id']}/cancel")
    assert r.status_code == 404


async def test_generic_task_cancel_finalizes_chat(client):
    data = await login(client, "cs-cancel2@example.com")
    ws_id = data["workspaces"][0]["id"]
    agent = await _mk_agent(client, ws_id, "Canceler2")
    session = await _mk_session(client, ws_id, agent["id"])
    r = await client.post(f"/api/chat/{session['id']}/messages", json={"content": "outra pergunta"})
    task_id = r.json()["task_id"]

    # POST /api/tasks/{id}/cancel genérico também finaliza na sessão
    r = await client.post(f"/api/tasks/{task_id}/cancel")
    assert r.status_code == 200, r.text
    r = await client.get(f"/api/chat/{session['id']}/draft-restores")
    assert len(r.json()) == 1
    r = await client.get(f"/api/chat/{session['id']}/messages")
    assert r.json() == []


# ── chat: unread / mark-read ──────────────────────────────────────────
async def test_chat_unread_and_mark_read(client):
    data = await login(client, "cs-unread@example.com")
    ws_id = data["workspaces"][0]["id"]
    agent = await _mk_agent(client, ws_id, "Unreader")
    session = await _mk_session(client, ws_id, agent["id"])

    r = await client.post(f"/api/chat/{session['id']}/messages", json={"content": "oi"})
    task_id = r.json()["task_id"]
    await _run_task(client, ws_id, task_id)  # daemon completa → marca unread

    r = await client.get(f"/api/chat/{session['id']}")
    assert r.json()["has_unread"] is True
    r = await client.get("/api/chat/sessions", params={"workspace_id": ws_id})
    assert any(s["id"] == session["id"] and s["has_unread"] for s in r.json())

    r = await client.post(f"/api/chat/{session['id']}/read")
    assert r.status_code == 200
    assert r.json()["has_unread"] is False
    assert r.json()["last_read_at"] is not None


# ── chat: sessão arquivada somente leitura + delete cancela pendente ──
async def test_archived_session_read_only_and_safe_delete(client):
    data = await login(client, "cs-arch@example.com")
    ws_id = data["workspaces"][0]["id"]
    agent = await _mk_agent(client, ws_id, "Archiver")
    session = await _mk_session(client, ws_id, agent["id"])

    r = await client.patch(f"/api/chat/{session['id']}", json={"archived": True})
    assert r.json()["archived"] is True
    r = await client.post(f"/api/chat/{session['id']}/messages", json={"content": "bloqueia?"})
    assert r.status_code == 409  # somente leitura

    # desarquiva, envia, deleta com task pendente → task cancelada
    await client.patch(f"/api/chat/{session['id']}", json={"archived": False})
    r = await client.post(f"/api/chat/{session['id']}/messages", json={"content": "vai rodar"})
    task_id = r.json()["task_id"]
    r = await client.delete(f"/api/chat/{session['id']}")
    assert r.status_code == 200
    r = await client.get(f"/api/tasks/{task_id}")
    assert r.json()["status"] == "cancelled"
    assert r.json()["cancel_requested"] is True


# ── chat: pinned agents ───────────────────────────────────────────────
async def test_pinned_agents(client):
    data = await login(client, "cs-pins@example.com")
    ws_id = data["workspaces"][0]["id"]
    a1 = await _mk_agent(client, ws_id, "Pin1")
    a2 = await _mk_agent(client, ws_id, "Pin2")

    r = await client.post("/api/chat/pinned-agents", json={"workspace_id": ws_id, "agent_id": a1["id"]})
    assert r.status_code == 201, r.text
    # idempotente
    r = await client.post("/api/chat/pinned-agents", json={"workspace_id": ws_id, "agent_id": a1["id"]})
    assert r.status_code == 201
    await client.post("/api/chat/pinned-agents", json={"workspace_id": ws_id, "agent_id": a2["id"]})

    r = await client.get("/api/chat/pinned-agents", params={"workspace_id": ws_id})
    ids = [p["agent_id"] for p in r.json()]
    assert ids == [a1["id"], a2["id"]]

    # agente arquivado some da listagem
    await client.post(f"/api/agents/{a2['id']}/archive")
    r = await client.get("/api/chat/pinned-agents", params={"workspace_id": ws_id})
    assert [p["agent_id"] for p in r.json()] == [a1["id"]]

    r = await client.delete(f"/api/chat/pinned-agents/{a1['id']}", params={"workspace_id": ws_id})
    assert r.json()["ok"] is True
    r = await client.get("/api/chat/pinned-agents", params={"workspace_id": ws_id})
    assert r.json() == []


# ── chat: sanitização do título gerado por LLM ────────────────────────
async def test_title_sanitization_and_fallback(client):
    from ryu.services.chat import sanitize_title

    assert sanitize_title('"Título: Corrigir o build!"') == "Corrigir o build"
    assert sanitize_title("Title - Deploy pipeline.") == "Deploy pipeline"
    assert len(sanitize_title("x" * 200)) <= 60

    # sem LLM configurado: título truncado da primeira mensagem (fallback)
    data = await login(client, "cs-title@example.com")
    ws_id = data["workspaces"][0]["id"]
    agent = await _mk_agent(client, ws_id, "Titler")
    session = await _mk_session(client, ws_id, agent["id"])
    await client.post(f"/api/chat/{session['id']}/messages", json={"content": "me ajuda com o deploy"})
    r = await client.get(f"/api/chat/{session['id']}")
    assert r.json()["title"] == "me ajuda com o deploy"


# ── squads: assignee_type='squad' + briefing + loop de delegação ──────
async def _mk_squad(client, ws_id: str, leader_id: str, name: str = "Alpha") -> dict:
    r = await client.post(
        "/api/squads",
        json={
            "workspace_id": ws_id,
            "name": name,
            "leader_agent_id": leader_id,
            "description": "Squad de testes",
            "instructions": "Sempre priorize bugs.",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_squad_assignee_first_class_and_briefing(client):
    data = await login(client, "cs-squad@example.com")
    ws_id = data["workspaces"][0]["id"]
    leader = await _mk_agent(client, ws_id, "Leader")
    worker = await _mk_agent(client, ws_id, "Worker")
    squad = await _mk_squad(client, ws_id, leader["id"])
    assert squad["description"] == "Squad de testes"
    r = await client.post(
        f"/api/squads/{squad['id']}/members",
        json={"member_type": "agent", "member_id": worker["id"], "role": "backend"},
    )
    assert r.status_code == 204

    # PATCH /api/issues com assignee_type='squad' — issue PERMANECE na squad
    r = await client.post("/api/issues", json={"workspace_id": ws_id, "title": "Feature X"})
    issue = r.json()
    r = await client.patch(
        f"/api/issues/{issue['id']}",
        json={"assignee_type": "squad", "assignee_id": squad["id"], "status": "todo"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["assignee_type"] == "squad"
    assert r.json()["assignee_id"] == squad["id"]

    # briefing do líder enfileirado, com protocolo + roster + instructions
    r = await client.get("/api/tasks", params={"workspace_id": ws_id, "issue_id": issue["id"]})
    tasks = r.json()
    assert len(tasks) == 1
    assert tasks[0]["agent_id"] == leader["id"]
    prompt = tasks[0]["prompt"]
    assert "Sempre priorize bugs." in prompt  # instructions da squad
    assert "backend" in prompt  # roster com papel
    assert "squad-evaluated" in prompt  # endpoint de avaliação no protocolo

    # dedup: repatch não duplica task pendente
    r = await client.patch(f"/api/issues/{issue['id']}", json={"status": "in_progress"})
    r = await client.get("/api/tasks", params={"workspace_id": ws_id, "issue_id": issue["id"]})
    assert len(r.json()) == 1


async def test_squad_backlog_promotion_triggers_briefing(client):
    data = await login(client, "cs-squad-promo@example.com")
    ws_id = data["workspaces"][0]["id"]
    leader = await _mk_agent(client, ws_id, "PromoLead")
    squad = await _mk_squad(client, ws_id, leader["id"], name="Promo")
    r = await client.post(
        "/api/issues",
        json={
            "workspace_id": ws_id,
            "title": "Fica no backlog",
            "assignee_type": "squad",
            "assignee_id": squad["id"],
        },
    )
    issue = r.json()
    r = await client.get("/api/tasks", params={"workspace_id": ws_id, "issue_id": issue["id"]})
    assert r.json() == []  # backlog não dispara
    await client.patch(f"/api/issues/{issue['id']}", json={"status": "todo"})
    r = await client.get("/api/tasks", params={"workspace_id": ws_id, "issue_id": issue["id"]})
    assert len(r.json()) == 1  # promoção backlog→todo dispara briefing


async def test_comment_wakes_squad_leader(client):
    import asyncio

    from tests.conftest import run_task_through_daemon

    data = await login(client, "cs-squad-wake@example.com")
    ws_id = data["workspaces"][0]["id"]
    leader = await _mk_agent(client, ws_id, "WakeLead")
    squad = await _mk_squad(client, ws_id, leader["id"], name="Wake")
    r = await client.post(
        "/api/issues",
        json={
            "workspace_id": ws_id,
            "title": "Loop de delegação",
            "status": "todo",
            "assignee_type": "squad",
            "assignee_id": squad["id"],
        },
    )
    issue = r.json()
    r = await client.get("/api/tasks", params={"workspace_id": ws_id, "issue_id": issue["id"]})
    briefing = r.json()[0]
    await run_task_through_daemon(client, ws_id, task_id=briefing["id"])  # briefing pelo daemon
    await asyncio.sleep(0)

    # comentário humano re-aciona o líder (nova task com o comentário no contexto)
    r = await client.post(f"/api/issues/{issue['id']}/comments", json={"body": "terminei a parte 1"})
    assert r.status_code == 201, r.text
    r = await client.get("/api/tasks", params={"workspace_id": ws_id, "issue_id": issue["id"]})
    tasks = sorted(r.json(), key=lambda t: t["created_at"])
    queued = [t for t in tasks if t["status"] == "queued"]
    assert len(queued) == 1, tasks
    assert "terminei a parte 1" in queued[0]["prompt"]
    assert queued[0]["agent_id"] == leader["id"]

    # dedup: segundo comentário com task pendente não duplica
    await client.post(f"/api/issues/{issue['id']}/comments", json={"body": "mais contexto"})
    r = await client.get("/api/tasks", params={"workspace_id": ws_id, "issue_id": issue["id"]})
    assert len([t for t in r.json() if t["status"] == "queued"]) == 1


async def test_squad_mention_wakes_leader(client):
    data = await login(client, "cs-squad-mention@example.com")
    ws_id = data["workspaces"][0]["id"]
    leader = await _mk_agent(client, ws_id, "MentionLead")
    await _mk_squad(client, ws_id, leader["id"], name="Guardians")
    # issue SEM assignee de squad — menção @guardians aciona o líder
    r = await client.post("/api/issues", json={"workspace_id": ws_id, "title": "Solta", "status": "todo"})
    issue = r.json()
    r = await client.post(f"/api/issues/{issue['id']}/comments", json={"body": "@guardians podem olhar?"})
    assert r.status_code == 201
    r = await client.get("/api/tasks", params={"workspace_id": ws_id, "issue_id": issue["id"]})
    tasks = r.json()
    assert len(tasks) == 1 and tasks[0]["agent_id"] == leader["id"]


async def test_squad_evaluation_records_and_suppresses_leader_comment(client):
    from ryu.services.auth import create_task_token

    data = await login(client, "cs-squad-eval@example.com")
    ws_id = data["workspaces"][0]["id"]
    leader = await _mk_agent(client, ws_id, "EvalLead")
    squad = await _mk_squad(client, ws_id, leader["id"], name="Eval")
    r = await client.post(
        "/api/issues",
        json={
            "workspace_id": ws_id,
            "title": "Avaliação",
            "status": "todo",
            "assignee_type": "squad",
            "assignee_id": squad["id"],
        },
    )
    issue = r.json()
    r = await client.get("/api/tasks", params={"workspace_id": ws_id, "issue_id": issue["id"]})
    task = r.json()[0]

    # líder autentica com token rat_ e registra no_action
    rat = await create_task_token(leader["id"], task["id"], ws_id)
    headers = {"Authorization": f"Bearer {rat}"}
    r = await client.post(
        f"/api/issues/{issue['id']}/squad-evaluated",
        json={"outcome": "no_action", "squad_id": squad["id"]},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["outcome"] == "no_action"

    # outcome inválido → 400
    r = await client.post(
        f"/api/issues/{issue['id']}/squad-evaluated", json={"outcome": "meh"}, headers=headers
    )
    assert r.status_code == 400

    # no_action suprime o comentário do líder nesta rodada
    r = await client.post(
        f"/api/issues/{issue['id']}/comments", json={"body": "nada a fazer"}, headers=headers
    )
    assert r.status_code == 409, r.text

    # humano comenta normalmente (e o comentário re-aciona o líder)
    r = await client.post(f"/api/issues/{issue['id']}/comments", json={"body": "ok, valeu"})
    assert r.status_code == 201


async def test_squad_member_role_and_status(client):
    data = await login(client, "cs-squad-status@example.com")
    ws_id = data["workspaces"][0]["id"]
    leader = await _mk_agent(client, ws_id, "StatLead")
    worker = await _mk_agent(client, ws_id, "StatWorker")
    archived = await _mk_agent(client, ws_id, "StatOld")
    squad = await _mk_squad(client, ws_id, leader["id"], name="Stat")
    await client.post(
        f"/api/squads/{squad['id']}/members",
        json={"member_type": "agent", "member_id": worker["id"]},
    )
    await client.post(
        f"/api/squads/{squad['id']}/members",
        json={"member_type": "agent", "member_id": archived["id"]},
    )
    await client.post(f"/api/agents/{archived['id']}/archive")

    # PATCH role
    r = await client.patch(
        f"/api/squads/{squad['id']}/members/role",
        json={"member_id": worker["id"], "role": "frontend"},
    )
    assert r.status_code == 200 and r.json()["role"] == "frontend"

    # worker com task ativa (dispatched) → working, com a issue listada
    r = await client.post(
        "/api/issues",
        json={
            "workspace_id": ws_id,
            "title": "Em andamento",
            "status": "todo",
            "assignee_type": "agent",
            "assignee_id": worker["id"],
        },
    )
    issue = r.json()
    r = await client.get("/api/tasks", params={"workspace_id": ws_id, "issue_id": issue["id"]})
    task_id = r.json()[0]["id"]
    from sqlalchemy import update

    from ryu.db import SessionLocal
    from ryu.models import AgentTask

    async with SessionLocal() as db:
        await db.execute(update(AgentTask).where(AgentTask.id == task_id).values(status="running"))
        await db.commit()

    r = await client.get(f"/api/squads/{squad['id']}/members/status")
    assert r.status_code == 200, r.text
    by_id = {m["member_id"]: m for m in r.json()}
    assert by_id[leader["id"]]["is_leader"] is True
    assert by_id[leader["id"]]["status"] == "idle"
    assert by_id[worker["id"]]["status"] == "working"
    assert by_id[worker["id"]]["role"] == "frontend"
    assert any(i["id"] == issue["id"] for i in by_id[worker["id"]]["issues"])
    assert by_id[archived["id"]]["status"] == "archived"
