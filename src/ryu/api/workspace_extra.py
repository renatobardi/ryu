"""Extras de workspace: Search, My Issues, Runtimes e Settings.

- `search_router`: JSON, montar em main.py com prefix="/api/search".
- `pages_router`: páginas HTML (/w/{slug}/my-issues, /search, /runtimes, /settings), SEM prefixo.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import get_db
from ryu.models import Agent, ChatSession, Issue, Member, User
from ryu.realtime.hub import hub
from ryu.services.auth import current_user, current_workspace

search_router = APIRouter()
pages_router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

STATUS_ORDER = ["in_progress", "in_review", "todo", "blocked", "backlog", "done", "cancelled"]
STATUS_TITLES = {
    "backlog": "Backlog",
    "todo": "Todo",
    "in_progress": "In Progress",
    "in_review": "In Review",
    "done": "Done",
    "blocked": "Blocked",
    "cancelled": "Cancelled",
}

RUNTIME_CLIS = ["claude", "codex", "gemini", "git", "node"]


# ── Search ────────────────────────────────────────────────────────────
async def _search(db: AsyncSession, workspace_id: str, q: str, limit: int = 20) -> dict:
    like = f"%{q}%"
    issues = list(
        (
            await db.execute(
                select(Issue)
                .where(
                    Issue.workspace_id == workspace_id,
                    Issue.title.ilike(like) | Issue.description.ilike(like) | Issue.key.ilike(like),
                )
                .order_by(Issue.updated_at.desc())
                .limit(limit)
            )
        ).scalars()
    )
    agents = list(
        (
            await db.execute(
                select(Agent)
                .where(Agent.workspace_id == workspace_id, Agent.name.ilike(like) | Agent.handle.ilike(like))
                .order_by(Agent.name)
                .limit(limit)
            )
        ).scalars()
    )
    chats = list(
        (
            await db.execute(
                select(ChatSession)
                .where(ChatSession.workspace_id == workspace_id, ChatSession.title.ilike(like))
                .order_by(ChatSession.updated_at.desc())
                .limit(limit)
            )
        ).scalars()
    )
    return {"issues": issues, "agents": agents, "chats": chats}


@search_router.get("")
async def api_search(
    workspace_id: str,
    q: str = "",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    q = q.strip()
    if not q:
        return {"query": q, "issues": [], "agents": [], "chat_sessions": []}
    res = await _search(db, workspace_id, q)
    return {
        "query": q,
        "issues": [
            {"id": i.id, "key": i.key, "title": i.title, "status": i.status, "priority": i.priority}
            for i in res["issues"]
        ],
        "agents": [
            {"id": a.id, "name": a.name, "handle": a.handle, "status": a.status}
            for a in res["agents"]
        ],
        "chat_sessions": [
            {"id": c.id, "title": c.title, "agent_id": c.agent_id}
            for c in res["chats"]
        ],
    }


@pages_router.get("/w/{slug}/search", response_class=HTMLResponse)
async def search_page(
    slug: str,
    request: Request,
    q: str = "",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await current_workspace(slug, db, user)
    q = q.strip()
    res = await _search(db, ws.id, q) if q else {"issues": [], "agents": [], "chats": []}
    ctx = {
        "request": request, "user": user, "workspace": ws, "active_nav": "search",
        "q": q, "issues": res["issues"], "agents": res["agents"], "chats": res["chats"],
        "status_titles": STATUS_TITLES,
    }
    # requisição HTMX da barra da sidebar → só o fragmento de resultados
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("workspace/_search_results.html", ctx)
    return templates.TemplateResponse("workspace/search.html", ctx)


# ── My Issues ─────────────────────────────────────────────────────────
@pages_router.get("/w/{slug}/my-issues", response_class=HTMLResponse)
async def my_issues_page(slug: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    ws = await current_workspace(slug, db, user)
    row = await db.execute(select(Member).where(Member.workspace_id == ws.id, Member.user_id == user.id))
    member = row.scalars().first()
    grouped: dict[str, list[Issue]] = {st: [] for st in STATUS_ORDER}
    total = 0
    if member is not None:
        rows = await db.execute(
            select(Issue)
            .where(
                Issue.workspace_id == ws.id,
                Issue.assignee_type == "member",
                Issue.assignee_id.in_([member.id, user.id]),
            )
            .order_by(Issue.position)
        )
        for issue in rows.scalars():
            grouped.setdefault(issue.status, []).append(issue)
            total += 1
    return templates.TemplateResponse(
        "workspace/my_issues.html",
        {"request": request, "user": user, "workspace": ws, "active_nav": "my_issues",
         "grouped": grouped, "status_order": STATUS_ORDER, "status_titles": STATUS_TITLES, "total": total},
    )


# ── Runtimes ──────────────────────────────────────────────────────────
@pages_router.get("/w/{slug}/runtimes", response_class=HTMLResponse)
async def runtimes_page(slug: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    ws = await current_workspace(slug, db, user)
    runtimes = [{"name": cli, "path": shutil.which(cli), "available": shutil.which(cli) is not None} for cli in RUNTIME_CLIS]
    return templates.TemplateResponse(
        "workspace/runtimes.html",
        {"request": request, "user": user, "workspace": ws, "active_nav": "runtimes", "runtimes": runtimes},
    )


# ── Settings ──────────────────────────────────────────────────────────
@pages_router.get("/w/{slug}/settings", response_class=HTMLResponse)
async def settings_page(slug: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    ws = await current_workspace(slug, db, user)
    return templates.TemplateResponse(
        "workspace/settings.html",
        {"request": request, "user": user, "workspace": ws, "active_nav": "settings", "saved": request.query_params.get("saved")},
    )


@pages_router.post("/w/{slug}/settings", response_class=HTMLResponse)
async def settings_update(
    slug: str,
    request: Request,
    name: str = Form(...),
    issue_prefix: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await current_workspace(slug, db, user)
    if name.strip():
        ws.name = name.strip()
    prefix = issue_prefix.strip().upper()
    if prefix:
        ws.issue_prefix = prefix
    await db.commit()
    await hub.publish(ws.id, "workspace:updated", {"id": ws.id, "name": ws.name, "issue_prefix": ws.issue_prefix})
    return RedirectResponse(f"/w/{slug}/settings?saved=1", status_code=303)
