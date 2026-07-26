"""API + páginas do domínio INBOX + USAGE.

- `router`: rotas JSON do inbox, montar em main.py com prefix="/api/inbox".
- `usage_router`: rotas JSON de usage, montar com prefix="/api/usage".
- `pages_router`: páginas HTML (/w/{slug}/inbox, /w/{slug}/usage), montar SEM prefixo.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import get_db
from ryu.models import User, Workspace
from ryu.services import inbox as svc
from ryu.services.auth import current_user

router = APIRouter()
usage_router = APIRouter()
pages_router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

SEVERITY_TITLES = {
    "action_required": "Action Required",
    "attention": "Attention",
    "info": "Info",
}


class ItemIds(BaseModel):
    item_ids: list[str]


async def _workspace_by_slug(db: AsyncSession, slug: str) -> Workspace:
    row = await db.execute(select(Workspace).where(Workspace.slug == slug))
    ws = row.scalar_one_or_none()
    if ws is None:
        raise HTTPException(404, "workspace não encontrado")
    return ws


# ── Inbox JSON ────────────────────────────────────────────────────────
@router.get("")
async def list_inbox(
    workspace_id: str,
    read: bool | None = None,
    severity: str | None = None,
    archived: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    items = await svc.list_items(db, workspace_id, user.id, read=read, severity=severity, archived=archived)
    return [svc.item_to_dict(i) for i in items]


@router.get("/unread-count")
async def get_unread_count(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    return {"unread": await svc.unread_count(db, workspace_id, user.id)}


@router.post("/mark-read")
async def mark_read(
    payload: ItemIds,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    return {"updated": await svc.mark_read(db, user.id, payload.item_ids)}


@router.post("/mark-all-read")
async def mark_all_read(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    return {"updated": await svc.mark_all_read(db, workspace_id, user.id)}


@router.post("/archive")
async def archive(
    payload: ItemIds,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    return {"updated": await svc.archive_items(db, user.id, payload.item_ids)}


@router.post("/archive-all")
async def archive_all(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    return {"count": await svc.archive_all(db, workspace_id, user.id)}


@router.post("/archive-all-read")
async def archive_all_read(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    return {"count": await svc.archive_all_read(db, workspace_id, user.id)}


@router.post("/archive-completed")
async def archive_completed(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    return {"count": await svc.archive_completed(db, workspace_id, user.id)}


@router.get("/unread-summary")
async def unread_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    return await svc.unread_summary(db, user.id)


@router.get("/archived")
async def list_archived(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    items = await svc.list_items(db, workspace_id, user.id, archived=True, limit=200)
    return [svc.item_to_dict(i) for i in items]


@router.post("/{item_id}/unarchive")
async def unarchive(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    item = await svc.unarchive_item(db, user.id, item_id)
    if item is None:
        raise HTTPException(404, "item não encontrado")
    return svc.item_to_dict(item)


# ── Usage JSON ────────────────────────────────────────────────────────
@usage_router.get("/summary")
async def get_usage_summary(
    workspace_id: str,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    days = max(1, min(days, 365))
    return await svc.usage_summary(db, workspace_id, days)


# ── Páginas HTML ──────────────────────────────────────────────────────
async def _inbox_ctx(db: AsyncSession, ws: Workspace, user: User, read: bool | None, severity: str | None) -> dict:
    items = await svc.list_items(db, ws.id, user.id, read=read, severity=severity)
    return {
        "workspace": ws,
        "user": user,
        "items": items,
        "unread": await svc.unread_count(db, ws.id, user.id),
        "severity_titles": SEVERITY_TITLES,
        "filter_read": read,
        "filter_severity": severity,
    }


@pages_router.get("/w/{slug}/inbox", response_class=HTMLResponse)
async def inbox_page(
    slug: str,
    request: Request,
    read: bool | None = None,
    severity: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    ctx = await _inbox_ctx(db, ws, user, read, severity)
    ctx["request"] = request
    return templates.TemplateResponse("inbox/index.html", ctx)


@pages_router.post("/w/{slug}/inbox/mark-all-read", response_class=HTMLResponse)
async def inbox_page_mark_all(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    await svc.mark_all_read(db, ws.id, user.id)
    ctx = await _inbox_ctx(db, ws, user, None, None)
    ctx["request"] = request
    return templates.TemplateResponse("inbox/_items.html", ctx)


@pages_router.post("/w/{slug}/inbox/item-action", response_class=HTMLResponse)
async def inbox_page_item_action(
    slug: str,
    request: Request,
    item_id: str = Form(...),
    action: str = Form(...),  # read|archive
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    if action == "archive":
        await svc.archive_items(db, user.id, [item_id])
    else:
        await svc.mark_read(db, user.id, [item_id])
    ctx = await _inbox_ctx(db, ws, user, None, None)
    ctx["request"] = request
    return templates.TemplateResponse("inbox/_items.html", ctx)


@pages_router.get("/w/{slug}/usage", response_class=HTMLResponse)
async def usage_page(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    summary = await svc.usage_summary(db, ws.id, 30)
    return templates.TemplateResponse(
        "inbox/usage.html",
        {"request": request, "user": user, "workspace": ws, "summary": summary},
    )
