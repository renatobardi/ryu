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
    return ws, {
        "request": request,
        "workspace": ws,
        "sessions": sessions,
        "agents": agents,
        "user": user,
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
    messages = await chat_service.list_messages(db, session.id)
    ctx.update({"active_session": session, "messages": messages})
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
    messages = await chat_service.list_messages(db, session.id)
    return templates.TemplateResponse(
        "chat/messages.html",
        {"request": request, "messages": messages, "active_session": session},
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
    messages = await chat_service.list_messages(db, session.id)
    return templates.TemplateResponse(
        "chat/messages.html",
        {"request": request, "messages": messages, "active_session": session},
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
