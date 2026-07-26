"""Rotas de chat.

`router` (montado em /api/chat pelo main.py):
- POST   /sessions                     cria sessão (workspace_id ou slug + agent_id)
- GET    /sessions                     lista sessões do usuário no workspace
- GET    /{session_id}                 detalhe da sessão
- PATCH  /{session_id}                 renomear / arquivar / fixar
- DELETE /{session_id}                 apaga sessão + mensagens
- GET    /{session_id}/messages        lista mensagens
- POST   /{session_id}/messages        cria ChatMessage(role='user') + AgentTask(kind='chat')

`pages_router` (montar SEM prefixo no main.py — páginas HTML):
- GET /w/{slug}/chat                   lista de sessões + tela vazia
- GET /w/{slug}/chat/{session_id}      conversa
- GET /w/{slug}/chat/{session_id}/partial/messages  (partial HTMX polling)
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import get_db
from ryu.models import Agent, User, Workspace
from ryu.services import chat as chat_service
from ryu.services.auth import current_user, current_workspace

router = APIRouter()
pages_router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ── Schemas ───────────────────────────────────────────────────────────
class SessionCreateIn(BaseModel):
    agent_id: str
    workspace_id: str | None = None
    workspace_slug: str | None = None
    title: str = "Nova conversa"


class SessionUpdateIn(BaseModel):
    title: str | None = None
    archived: bool | None = None
    pinned: bool | None = None


class MessageIn(BaseModel):
    content: str


def _session_out(s) -> dict:
    return {
        "id": s.id,
        "workspace_id": s.workspace_id,
        "agent_id": s.agent_id,
        "title": s.title,
        "archived": s.archived,
        "pinned": s.pinned,
        "has_unread": getattr(s, "unread_since", None) is not None,
        "unread_since": getattr(s, "unread_since", None),
        "last_read_at": getattr(s, "last_read_at", None),
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


def _message_out(m) -> dict:
    return {
        "id": m.id,
        "session_id": m.session_id,
        "role": m.role,
        "content": m.content,
        "created_at": m.created_at,
    }


async def _resolve_workspace_id(
    db: AsyncSession,
    user: User,
    workspace_id: str | None,
    workspace_slug: str | None,
) -> str:
    if workspace_id:
        res = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        ws = res.scalars().first()
        if ws is None:
            raise HTTPException(status_code=404, detail="Workspace não encontrado")
        await current_workspace(ws.slug, db, user)  # valida membership
        return ws.id
    if workspace_slug:
        ws = await current_workspace(workspace_slug, db, user)
        return ws.id
    raise HTTPException(status_code=422, detail="Informe workspace_id ou workspace_slug")


# ── CRUD de sessões ───────────────────────────────────────────────────
@router.post("/sessions")
async def create_session(
    body: SessionCreateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ws_id = await _resolve_workspace_id(db, user, body.workspace_id, body.workspace_slug)
    session = await chat_service.create_session(
        db, workspace_id=ws_id, user_id=user.id, agent_id=body.agent_id, title=body.title
    )
    return _session_out(session)


@router.get("/sessions")
async def list_sessions(
    workspace_id: str | None = Query(default=None),
    workspace_slug: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ws_id = await _resolve_workspace_id(db, user, workspace_id, workspace_slug)
    sessions = await chat_service.list_sessions(
        db, workspace_id=ws_id, user_id=user.id, include_archived=include_archived
    )
    return [_session_out(s) for s in sessions]


# ── Pinned agents (barra de quick-agents) — ANTES de /{session_id} ────
class PinAgentIn(BaseModel):
    agent_id: str
    workspace_id: str | None = None
    workspace_slug: str | None = None


@router.get("/pinned-agents")
async def list_pinned_agents(
    workspace_id: str | None = Query(default=None),
    workspace_slug: str | None = Query(default=None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ws_id = await _resolve_workspace_id(db, user, workspace_id, workspace_slug)
    agents = await chat_service.list_pinned_agents(db, workspace_id=ws_id, user_id=user.id)
    return [
        {"agent_id": a.id, "name": a.name, "handle": a.handle, "description": a.description}
        for a in agents
    ]


@router.post("/pinned-agents", status_code=201)
async def pin_agent(
    body: PinAgentIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ws_id = await _resolve_workspace_id(db, user, body.workspace_id, body.workspace_slug)
    pin = await chat_service.pin_agent(db, workspace_id=ws_id, user_id=user.id, agent_id=body.agent_id)
    return {"agent_id": pin.agent_id, "position": pin.position}


@router.delete("/pinned-agents/{agent_id}")
async def unpin_agent(
    agent_id: str,
    workspace_id: str | None = Query(default=None),
    workspace_slug: str | None = Query(default=None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ws_id = await _resolve_workspace_id(db, user, workspace_id, workspace_slug)
    await chat_service.unpin_agent(db, workspace_id=ws_id, user_id=user.id, agent_id=agent_id)
    return {"ok": True}


# ── Pending tasks agregados (FAB) — ANTES de /{session_id} ────────────
@router.get("/pending-tasks")
async def list_pending_tasks(
    workspace_id: str | None = Query(default=None),
    workspace_slug: str | None = Query(default=None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ws_id = await _resolve_workspace_id(db, user, workspace_id, workspace_slug)
    tasks = await chat_service.list_pending_tasks(db, workspace_id=ws_id, user_id=user.id)
    return [chat_service.pending_task_out(t) for t in tasks]


@router.get("/pending-tasks/has-any")
async def has_pending_tasks(
    workspace_id: str | None = Query(default=None),
    workspace_slug: str | None = Query(default=None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ws_id = await _resolve_workspace_id(db, user, workspace_id, workspace_slug)
    tasks = await chat_service.list_pending_tasks(db, workspace_id=ws_id, user_id=user.id)
    return {"has_any": len(tasks) > 0, "count": len(tasks)}


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await chat_service.get_session(db, session_id, user.id)
    return _session_out(session)


@router.patch("/{session_id}")
async def update_session(
    session_id: str,
    body: SessionUpdateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await chat_service.get_session(db, session_id, user.id)
    session = await chat_service.update_session(
        db, session, title=body.title, archived=body.archived, pinned=body.pinned
    )
    return _session_out(session)


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await chat_service.get_session(db, session_id, user.id)
    await chat_service.delete_session(db, session)
    return {"ok": True}


# ── Mensagens ─────────────────────────────────────────────────────────
@router.get("/{session_id}/messages")
async def list_messages(
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await chat_service.get_session(db, session_id, user.id)
    messages = await chat_service.list_messages(db, session.id)
    return [_message_out(m) for m in messages]


@router.post("/{session_id}/messages", status_code=201)
async def post_message(
    session_id: str,
    body: MessageIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await chat_service.get_session(db, session_id, user.id)
    msg, task = await chat_service.add_user_message(db, session, body.content)
    return {"message": _message_out(msg), "task_id": task.id, "task_status": task.status}


# ── Pending task da sessão / read / cancel / draft-restores ───────────
@router.get("/{session_id}/pending-task")
async def get_pending_task(
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await chat_service.get_session(db, session_id, user.id)
    task = await chat_service.get_pending_task(db, session.id)
    return {"task": chat_service.pending_task_out(task)}


@router.post("/{session_id}/read")
async def mark_read(
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await chat_service.get_session(db, session_id, user.id)
    session = await chat_service.mark_session_read(db, session)
    return _session_out(session)


@router.post("/{session_id}/cancel")
async def cancel_pending(
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stop: cancela a task de chat pendente da sessão (draft restore quando
    a resposta ficou vazia)."""
    session = await chat_service.get_session(db, session_id, user.id)
    task, restore = await chat_service.cancel_pending_task(db, session)
    if task is None:
        raise HTTPException(status_code=404, detail="Nenhuma task pendente nesta sessão")
    return {
        "task_id": task.id,
        "status": task.status,
        "restore": chat_service.draft_restore_out(restore) if restore else None,
    }


@router.get("/{session_id}/draft-restores")
async def list_draft_restores(
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await chat_service.get_session(db, session_id, user.id)
    rows = await chat_service.list_draft_restores(db, session.id)
    return [chat_service.draft_restore_out(r) for r in rows]


@router.delete("/{session_id}/draft-restores/{restore_id}")
async def consume_draft_restore(
    session_id: str,
    restore_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Consome o restore (idempotente: já consumido → ok sem conteúdo)."""
    session = await chat_service.get_session(db, session_id, user.id)
    row = await chat_service.consume_draft_restore(db, session.id, restore_id)
    return {"ok": True, "restore": chat_service.draft_restore_out(row) if row else None}


# ── Páginas HTML (HTMX) ───────────────────────────────────────────────
async def _page_ctx(
    request: Request, slug: str, user: User, db: AsyncSession
) -> tuple[Workspace, dict]:
    ws = await current_workspace(slug, db, user)
    sessions = await chat_service.list_sessions(db, workspace_id=ws.id, user_id=user.id)
    res = await db.execute(
        select(Agent).where(Agent.workspace_id == ws.id).order_by(Agent.name)
    )
    agents = list(res.scalars().all())
    pinned_agents = await chat_service.list_pinned_agents(db, workspace_id=ws.id, user_id=user.id)
    return ws, {
        "request": request,
        "workspace": ws,
        "sessions": sessions,
        "agents": agents,
        "pinned_agents": pinned_agents,
        "user": user,
    }


async def _messages_ctx(
    request: Request, db: AsyncSession, session, *, mark_read: bool = False
) -> dict:
    """Contexto do partial de mensagens: inclui a task pendente e o transcript
    parcial (streaming da resposta do agente em andamento)."""
    messages = await chat_service.list_messages(db, session.id)
    pending_task = await chat_service.get_pending_task(db, session.id)
    partial = {"texts": [], "activity": []}
    if pending_task is not None and pending_task.status == "running":
        partial = await chat_service.partial_transcript(db, pending_task.id)
    if mark_read and getattr(session, "unread_since", None) is not None:
        # sessão está aberta/em foco — limpa o cursor de não-lido
        await chat_service.mark_session_read(db, session)
    return {
        "request": request,
        "messages": messages,
        "active_session": session,
        "pending_task": pending_task,
        "partial_texts": partial["texts"],
        "partial_activity": partial["activity"],
    }


@pages_router.get("/w/{slug}/chat", response_class=HTMLResponse)
async def chat_index(
    request: Request,
    slug: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    _, ctx = await _page_ctx(request, slug, user, db)
    ctx.update({"active_session": None, "messages": []})
    return templates.TemplateResponse("chat/index.html", ctx)


@pages_router.get("/w/{slug}/chat/{session_id}", response_class=HTMLResponse)
async def chat_session_page(
    request: Request,
    slug: str,
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    _, ctx = await _page_ctx(request, slug, user, db)
    session = await chat_service.get_session(db, session_id, user.id)
    ctx.update(await _messages_ctx(request, db, session, mark_read=True))
    return templates.TemplateResponse("chat/index.html", ctx)


@pages_router.get(
    "/w/{slug}/chat/{session_id}/partial/messages", response_class=HTMLResponse
)
async def chat_messages_partial(
    request: Request,
    slug: str,
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await current_workspace(slug, db, user)
    session = await chat_service.get_session(db, session_id, user.id)
    return templates.TemplateResponse(
        "chat/messages.html",
        await _messages_ctx(request, db, session, mark_read=True),
    )


@pages_router.post("/w/{slug}/chat/{session_id}/send", response_class=HTMLResponse)
async def chat_send_form(
    request: Request,
    slug: str,
    session_id: str,
    content: str = Form(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Envio via formulário HTMX — devolve o partial de mensagens atualizado."""
    await current_workspace(slug, db, user)
    session = await chat_service.get_session(db, session_id, user.id)
    await chat_service.add_user_message(db, session, content)
    return templates.TemplateResponse(
        "chat/messages.html", await _messages_ctx(request, db, session)
    )


@pages_router.post("/w/{slug}/chat/{session_id}/cancel", response_class=HTMLResponse)
async def chat_cancel_form(
    request: Request,
    slug: str,
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Botão 'parar' do composer — cancela a task pendente e devolve o partial."""
    await current_workspace(slug, db, user)
    session = await chat_service.get_session(db, session_id, user.id)
    await chat_service.cancel_pending_task(db, session)
    return templates.TemplateResponse(
        "chat/messages.html", await _messages_ctx(request, db, session)
    )


@pages_router.post("/w/{slug}/chat/new")
async def chat_new_session(
    slug: str,
    agent_id: str = Form(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ws = await current_workspace(slug, db, user)
    session = await chat_service.create_session(
        db, workspace_id=ws.id, user_id=user.id, agent_id=agent_id
    )
    return RedirectResponse(url=f"/w/{slug}/chat/{session.id}", status_code=303)


@pages_router.post("/w/{slug}/chat/pin-agent")
async def chat_pin_agent_form(
    slug: str,
    agent_id: str = Form(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ws = await current_workspace(slug, db, user)
    await chat_service.pin_agent(db, workspace_id=ws.id, user_id=user.id, agent_id=agent_id)
    return RedirectResponse(url=f"/w/{slug}/chat", status_code=303)


@pages_router.post("/w/{slug}/chat/unpin-agent/{agent_id}")
async def chat_unpin_agent_form(
    slug: str,
    agent_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ws = await current_workspace(slug, db, user)
    await chat_service.unpin_agent(db, workspace_id=ws.id, user_id=user.id, agent_id=agent_id)
    return RedirectResponse(url=f"/w/{slug}/chat", status_code=303)
