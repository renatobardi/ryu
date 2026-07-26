"""API + páginas do domínio AUTOPILOTS.

- `router`: rotas JSON, montar em main.py com prefix="/api/autopilots".
  Inclui o webhook público POST /api/autopilots/hook/{webhook_token} (sem auth).
- `pages_router`: páginas HTML (/w/{slug}/autopilots), montar SEM prefixo.
- Cron: main.py deve chamar `await automation.register_autopilot_jobs(scheduler)`
  no lifespan (AsyncIOScheduler do APScheduler já iniciado).
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
from ryu.models import Agent, User, Workspace
from ryu.services import automation as svc
from ryu.services.auth import current_user

router = APIRouter()
pages_router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _http(e: svc.AutomationError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=e.message)


class AutopilotCreate(BaseModel):
    workspace_id: str
    name: str
    rule: str = ""
    trigger_type: str = "cron"  # cron|webhook|manual
    cron_expr: str | None = None
    target_agent_id: str | None = None
    enabled: bool = True


class AutopilotPatch(BaseModel):
    name: str | None = None
    rule: str | None = None
    trigger_type: str | None = None
    cron_expr: str | None = None
    target_agent_id: str | None = None
    enabled: bool | None = None


# ── JSON API ──────────────────────────────────────────────────────────
@router.post("", status_code=201)
async def create_autopilot(payload: AutopilotCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        ap = await svc.create_autopilot(
            db,
            payload.workspace_id,
            name=payload.name,
            rule=payload.rule,
            trigger_type=payload.trigger_type,
            cron_expr=payload.cron_expr,
            target_agent_id=payload.target_agent_id,
            enabled=payload.enabled,
        )
    except svc.AutomationError as e:
        raise _http(e)
    return svc.autopilot_to_dict(ap)


@router.get("")
async def list_autopilots(workspace_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    return [svc.autopilot_to_dict(a) for a in await svc.list_autopilots(db, workspace_id)]


# webhook público — SEM auth (o token do path é o segredo)
@router.post("/hook/{webhook_token}")
async def webhook_trigger(webhook_token: str, db: AsyncSession = Depends(get_db)):
    try:
        ap = await svc.get_autopilot_by_token(db, webhook_token)
    except svc.AutomationError as e:
        raise _http(e)
    if not ap.enabled:
        raise HTTPException(status_code=409, detail="autopilot desabilitado")
    run = await svc.run_autopilot(db, ap, source="webhook")
    return svc.run_to_dict(run)


@router.get("/{autopilot_id}")
async def get_autopilot(autopilot_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        ap = await svc.get_autopilot(db, autopilot_id)
    except svc.AutomationError as e:
        raise _http(e)
    return svc.autopilot_to_dict(ap)


@router.patch("/{autopilot_id}")
async def patch_autopilot(
    autopilot_id: str, payload: AutopilotPatch, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        ap = await svc.update_autopilot(db, autopilot_id, payload.model_dump(exclude_unset=True))
    except svc.AutomationError as e:
        raise _http(e)
    return svc.autopilot_to_dict(ap)


@router.delete("/{autopilot_id}", status_code=204)
async def delete_autopilot(autopilot_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.delete_autopilot(db, autopilot_id)
    except svc.AutomationError as e:
        raise _http(e)


@router.post("/{autopilot_id}/run")
async def manual_run(autopilot_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        ap = await svc.get_autopilot(db, autopilot_id)
    except svc.AutomationError as e:
        raise _http(e)
    run = await svc.run_autopilot(db, ap, source="manual")
    return svc.run_to_dict(run)


@router.get("/{autopilot_id}/runs")
async def runs(autopilot_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.get_autopilot(db, autopilot_id)
    except svc.AutomationError as e:
        raise _http(e)
    return [svc.run_to_dict(r) for r in await svc.list_runs(db, autopilot_id)]


# ── Páginas HTML ──────────────────────────────────────────────────────
async def _workspace_by_slug(db: AsyncSession, slug: str) -> Workspace:
    row = await db.execute(select(Workspace).where(Workspace.slug == slug))
    ws = row.scalar_one_or_none()
    if ws is None:
        raise HTTPException(404, "workspace não encontrado")
    return ws


async def _autopilots_ctx(db: AsyncSession, ws: Workspace) -> dict:
    autopilots = await svc.list_autopilots(db, ws.id)
    agents = list((await db.execute(select(Agent).where(Agent.workspace_id == ws.id))).scalars())
    agent_names = {a.id: a.name for a in agents}
    return {"workspace": ws, "autopilots": autopilots, "agents": agents, "agent_names": agent_names}


@pages_router.get("/w/{slug}/autopilots", response_class=HTMLResponse)
async def autopilots_page(slug: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    ws = await _workspace_by_slug(db, slug)
    ctx = await _autopilots_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/autopilots.html", ctx)


@pages_router.post("/w/{slug}/autopilots", response_class=HTMLResponse)
async def autopilots_page_create(
    slug: str,
    request: Request,
    name: str = Form(...),
    rule: str = Form(""),
    trigger_type: str = Form("cron"),
    cron_expr: str = Form(""),
    target_agent_id: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    try:
        await svc.create_autopilot(
            db,
            ws.id,
            name=name,
            rule=rule,
            trigger_type=trigger_type,
            cron_expr=cron_expr or None,
            target_agent_id=target_agent_id or None,
        )
    except svc.AutomationError as e:
        raise _http(e)
    ctx = await _autopilots_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/_autopilots_list.html", ctx)


@pages_router.post("/w/{slug}/autopilots/{autopilot_id}/run", response_class=HTMLResponse)
async def autopilots_page_run(
    slug: str,
    autopilot_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    try:
        ap = await svc.get_autopilot(db, autopilot_id)
        await svc.run_autopilot(db, ap, source="manual")
    except svc.AutomationError as e:
        raise _http(e)
    ctx = await _autopilots_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/_autopilots_list.html", ctx)


@pages_router.post("/w/{slug}/autopilots/{autopilot_id}/toggle", response_class=HTMLResponse)
async def autopilots_page_toggle(
    slug: str,
    autopilot_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    try:
        ap = await svc.get_autopilot(db, autopilot_id)
        await svc.update_autopilot(db, autopilot_id, {"enabled": not ap.enabled})
    except svc.AutomationError as e:
        raise _http(e)
    ctx = await _autopilots_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/_autopilots_list.html", ctx)


@pages_router.post("/w/{slug}/autopilots/{autopilot_id}/delete", response_class=HTMLResponse)
async def autopilots_page_delete(
    slug: str,
    autopilot_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    try:
        await svc.delete_autopilot(db, autopilot_id)
    except svc.AutomationError as e:
        raise _http(e)
    ctx = await _autopilots_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/_autopilots_list.html", ctx)
