"""Páginas base do Ryu (UI BASE).

Exporta:
- `router`: montar SEM prefixo no main.py.
  - GET /            → redirect para /login (anônimo) ou /w/{slug} (logado)
  - GET /login       → tela de login (e-mail → código)
  - GET /w/{slug}    → dashboard do workspace

Pendências de integração (main.py, feito depois):
- app.mount("/static", StaticFiles(directory=".../ryu/web/static"), name="static")
- endpoint WebSocket /ws/{workspace_id} conectado ao hub (realtime).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import get_db
from ryu.models import Agent, AgentTask, Issue, Member, User, Workspace
from ryu.services.auth import current_user, current_workspace, optional_user

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

STATUS_ORDER = ["backlog", "todo", "in_progress", "in_review", "done", "blocked", "cancelled"]
STATUS_TITLES = {
    "backlog": "Backlog",
    "todo": "Todo",
    "in_progress": "In Progress",
    "in_review": "In Review",
    "done": "Done",
    "blocked": "Blocked",
    "cancelled": "Cancelled",
}


async def _first_workspace(db: AsyncSession, user: User) -> Workspace | None:
    res = await db.execute(
        select(Workspace)
        .join(Member, Member.workspace_id == Workspace.id)
        .where(Member.user_id == user.id)
        .order_by(Workspace.created_at)
    )
    return res.scalars().first()


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(optional_user),
):
    if user is None:
        return RedirectResponse("/login", status_code=302)
    ws = await _first_workspace(db, user)
    if ws is None:
        return RedirectResponse("/login", status_code=302)
    return RedirectResponse(f"/w/{ws.slug}", status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(optional_user),
):
    if user is not None:
        ws = await _first_workspace(db, user)
        if ws is not None:
            return RedirectResponse(f"/w/{ws.slug}", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/w/{slug}", response_class=HTMLResponse)
async def dashboard(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await current_workspace(slug, db, user)

    # Contagem de issues por status
    res = await db.execute(
        select(Issue.status, func.count(Issue.id))
        .where(Issue.workspace_id == ws.id)
        .group_by(Issue.status)
    )
    issue_counts = {status: count for status, count in res.all()}

    # Agents
    res = await db.execute(
        select(Agent).where(Agent.workspace_id == ws.id).order_by(Agent.name)
    )
    agents = list(res.scalars())
    agent_names = {a.id: a.name for a in agents}

    # Tasks recentes
    res = await db.execute(
        select(AgentTask)
        .where(AgentTask.workspace_id == ws.id)
        .order_by(AgentTask.created_at.desc())
        .limit(10)
    )
    recent_tasks = list(res.scalars())

    ctx = {
        "request": request,
        "user": user,
        "workspace": ws,
        "active_nav": "dashboard",
        "status_order": STATUS_ORDER,
        "status_titles": STATUS_TITLES,
        "issue_counts": issue_counts,
        "agents": agents,
        "agent_names": agent_names,
        "recent_tasks": recent_tasks,
    }
    return templates.TemplateResponse("dashboard.html", ctx)
