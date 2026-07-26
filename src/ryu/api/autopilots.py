"""API + páginas do domínio AUTOPILOTS.

- `router`: rotas JSON, montar em main.py com prefix="/api/autopilots".
  Inclui o webhook público POST /api/autopilots/hook/{token} (sem auth) —
  ingress persist-first com webhook_delivery, dedupe, HMAC e replay.
- `pages_router`: páginas HTML (/w/{slug}/autopilots), montar SEM prefixo.
- Cron: main.py deve chamar `await automation.register_autopilot_jobs(scheduler)`
  no lifespan (AsyncIOScheduler do APScheduler já iniciado).

Permissões (multica requireAutopilotWrite): escrita = criador ∪ owner/admin
do workspace ∪ colaboradores (autopilot_collaborator).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
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


class TriggerSpec(BaseModel):
    kind: str  # schedule|webhook|api
    enabled: bool = True
    label: str = ""
    cron_expression: str | None = None
    timezone: str = "UTC"
    provider: str = "generic"  # generic|github
    signing_secret: str | None = None
    event_filters: list | None = None


class AutopilotCreate(BaseModel):
    workspace_id: str
    name: str
    rule: str = ""
    trigger_type: str = "cron"  # cron|webhook|manual (legado)
    cron_expr: str | None = None
    target_agent_id: str | None = None
    enabled: bool = True
    status: str | None = None  # active|paused|archived
    execution_mode: str = "create_issue"  # create_issue|run_only
    issue_title_template: str | None = None
    subscribers: list[str] | None = None
    triggers: list[TriggerSpec] | None = None


class AutopilotPatch(BaseModel):
    name: str | None = None
    rule: str | None = None
    trigger_type: str | None = None
    cron_expr: str | None = None
    target_agent_id: str | None = None
    enabled: bool | None = None
    status: str | None = None
    execution_mode: str | None = None
    issue_title_template: str | None = None
    subscribers: list[str] | None = None


class TriggerPatch(BaseModel):
    enabled: bool | None = None
    label: str | None = None
    cron_expression: str | None = None
    timezone: str | None = None
    provider: str | None = None
    event_filters: list | None = None


class SigningSecretPut(BaseModel):
    signing_secret: str | None = None  # None/"" limpa o secret


class CollaboratorAdd(BaseModel):
    user_id: str


class ManualRunBody(BaseModel):
    trigger_id: str | None = None


async def _load_writable(
    db: AsyncSession, autopilot_id: str, user: User
) -> "svc.Autopilot":
    ap = await svc.get_autopilot(db, autopilot_id)
    await svc.require_autopilot_write(db, ap, user)
    return ap


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
            status=payload.status,
            execution_mode=payload.execution_mode,
            issue_title_template=payload.issue_title_template,
            subscribers=payload.subscribers,
            triggers=[t.model_dump() for t in payload.triggers] if payload.triggers else None,
            created_by_type="member",
            created_by_id=user.id,
        )
    except svc.AutomationError as e:
        raise _http(e)
    d = svc.autopilot_to_dict(ap)
    d["triggers"] = [svc.trigger_to_dict(t) for t in await svc.list_triggers(db, ap.id)]
    return d


@router.get("")
async def list_autopilots(workspace_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    return [svc.autopilot_to_dict(a) for a in await svc.list_autopilots(db, workspace_id)]


# webhook público — SEM auth (o token do path é o segredo). Persist-first:
# cada POST vira uma linha webhook_delivery (inclusive rejected/ignored).
@router.post("/hook/{webhook_token}")
async def webhook_trigger(webhook_token: str, request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    status_code, resp = await svc.webhook_ingress(
        db, webhook_token, body=body, headers=dict(request.headers)
    )
    return JSONResponse(resp, status_code=status_code)


@router.get("/{autopilot_id}")
async def get_autopilot(autopilot_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        ap = await svc.get_autopilot(db, autopilot_id)
    except svc.AutomationError as e:
        raise _http(e)
    d = svc.autopilot_to_dict(ap)
    d["triggers"] = [svc.trigger_to_dict(t) for t in await svc.list_triggers(db, ap.id)]
    d["subscribers"] = await svc.list_autopilot_subscribers(db, ap.id)
    d["collaborators"] = [
        {"user_id": c.user_id, "granted_by": c.granted_by}
        for c in await svc.list_collaborators(db, ap.id)
    ]
    d["can_write"] = await svc.can_write_autopilot(db, ap, user.id)
    return d


@router.patch("/{autopilot_id}")
async def patch_autopilot(
    autopilot_id: str, payload: AutopilotPatch, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        await _load_writable(db, autopilot_id, user)
        ap = await svc.update_autopilot(
            db, autopilot_id, payload.model_dump(exclude_unset=True),
            actor_type="member", actor_id=user.id,
        )
    except svc.AutomationError as e:
        raise _http(e)
    return svc.autopilot_to_dict(ap)


@router.delete("/{autopilot_id}", status_code=204)
async def delete_autopilot(autopilot_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await _load_writable(db, autopilot_id, user)
        await svc.delete_autopilot(db, autopilot_id)
    except svc.AutomationError as e:
        raise _http(e)


@router.post("/{autopilot_id}/run")
async def manual_run(
    autopilot_id: str,
    payload: ManualRunBody | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        ap = await _load_writable(db, autopilot_id, user)
        trigger = None
        source = "manual"
        if payload and payload.trigger_id:
            trigger = await svc.get_trigger(db, ap.id, payload.trigger_id)
            if trigger.kind == "api":
                source = "api"
        run = await svc.run_autopilot(db, ap, source=source, trigger=trigger)
    except svc.AutomationError as e:
        raise _http(e)
    return svc.run_to_dict(run)


@router.get("/{autopilot_id}/runs")
async def runs(autopilot_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.get_autopilot(db, autopilot_id)
    except svc.AutomationError as e:
        raise _http(e)
    return [svc.run_to_dict(r) for r in await svc.list_runs(db, autopilot_id)]


@router.get("/{autopilot_id}/runs/{run_id}")
async def run_detail(autopilot_id: str, run_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.get_autopilot(db, autopilot_id)
        run = await svc.get_run(db, autopilot_id, run_id)
    except svc.AutomationError as e:
        raise _http(e)
    return svc.run_to_dict(run)


@router.get("/{autopilot_id}/versions")
async def rule_versions(autopilot_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.get_autopilot(db, autopilot_id)
    except svc.AutomationError as e:
        raise _http(e)
    return [svc.rule_version_to_dict(v) for v in await svc.list_rule_versions(db, autopilot_id)]


# ── Triggers (multica 042) ────────────────────────────────────────────
@router.get("/{autopilot_id}/triggers")
async def list_triggers(autopilot_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.get_autopilot(db, autopilot_id)
    except svc.AutomationError as e:
        raise _http(e)
    return [svc.trigger_to_dict(t) for t in await svc.list_triggers(db, autopilot_id)]


@router.post("/{autopilot_id}/triggers", status_code=201)
async def create_trigger(
    autopilot_id: str, payload: TriggerSpec, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        ap = await _load_writable(db, autopilot_id, user)
        trig = await svc.create_trigger(db, ap, payload.model_dump(), "member", user.id)
    except svc.AutomationError as e:
        raise _http(e)
    return svc.trigger_to_dict(trig)


@router.patch("/{autopilot_id}/triggers/{trigger_id}")
async def patch_trigger(
    autopilot_id: str,
    trigger_id: str,
    payload: TriggerPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        ap = await _load_writable(db, autopilot_id, user)
        trig = await svc.update_trigger(
            db, ap, trigger_id, payload.model_dump(exclude_unset=True), "member", user.id
        )
    except svc.AutomationError as e:
        raise _http(e)
    return svc.trigger_to_dict(trig)


@router.delete("/{autopilot_id}/triggers/{trigger_id}", status_code=204)
async def delete_trigger(
    autopilot_id: str, trigger_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        ap = await _load_writable(db, autopilot_id, user)
        await svc.delete_trigger(db, ap, trigger_id, "member", user.id)
    except svc.AutomationError as e:
        raise _http(e)


@router.post("/{autopilot_id}/triggers/{trigger_id}/rotate-webhook-token")
async def rotate_webhook_token(
    autopilot_id: str, trigger_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        ap = await _load_writable(db, autopilot_id, user)
        trig = await svc.rotate_trigger_webhook_token(db, ap, trigger_id, "member", user.id)
    except svc.AutomationError as e:
        raise _http(e)
    return svc.trigger_to_dict(trig)


@router.put("/{autopilot_id}/triggers/{trigger_id}/signing-secret")
async def set_signing_secret(
    autopilot_id: str,
    trigger_id: str,
    payload: SigningSecretPut,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        ap = await _load_writable(db, autopilot_id, user)
        trig = await svc.set_trigger_signing_secret(
            db, ap, trigger_id, payload.signing_secret, "member", user.id
        )
    except svc.AutomationError as e:
        raise _http(e)
    return svc.trigger_to_dict(trig)


# ── Deliveries (multica 093 webhook_delivery) ─────────────────────────
@router.get("/{autopilot_id}/deliveries")
async def list_deliveries(
    autopilot_id: str,
    status: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        await svc.get_autopilot(db, autopilot_id)
    except svc.AutomationError as e:
        raise _http(e)
    return [
        svc.delivery_to_dict(d)
        for d in await svc.list_deliveries(db, autopilot_id, limit=min(max(limit, 1), 200), status=status)
    ]


@router.get("/{autopilot_id}/deliveries/{delivery_id}")
async def get_delivery(
    autopilot_id: str, delivery_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        await svc.get_autopilot(db, autopilot_id)
        d = await svc.get_delivery(db, autopilot_id, delivery_id)
    except svc.AutomationError as e:
        raise _http(e)
    return svc.delivery_to_dict(d, include_body=True)


@router.post("/{autopilot_id}/deliveries/{delivery_id}/replay")
async def replay_delivery(
    autopilot_id: str, delivery_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        ap = await _load_writable(db, autopilot_id, user)
        replay, run = await svc.replay_delivery(db, ap, delivery_id)
    except svc.AutomationError as e:
        raise _http(e)
    out = svc.delivery_to_dict(replay)
    out["run"] = svc.run_to_dict(run) if run is not None else None
    return out


# ── Collaborators (multica 128) ───────────────────────────────────────
@router.get("/{autopilot_id}/collaborators")
async def list_collaborators(autopilot_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.get_autopilot(db, autopilot_id)
    except svc.AutomationError as e:
        raise _http(e)
    return [
        {"user_id": c.user_id, "user_type": c.user_type, "granted_by": c.granted_by,
         "created_at": c.created_at.isoformat() if c.created_at else None}
        for c in await svc.list_collaborators(db, autopilot_id)
    ]


@router.post("/{autopilot_id}/collaborators", status_code=201)
async def add_collaborator(
    autopilot_id: str, payload: CollaboratorAdd, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        ap = await svc.get_autopilot(db, autopilot_id)
        await svc.require_autopilot_admin(db, ap, user)
        await svc.add_collaborator(db, ap, payload.user_id, granted_by=user.id)
    except svc.AutomationError as e:
        raise _http(e)
    return {"ok": True, "user_id": payload.user_id}


@router.delete("/{autopilot_id}/collaborators/{user_id}", status_code=204)
async def remove_collaborator(
    autopilot_id: str, user_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        ap = await svc.get_autopilot(db, autopilot_id)
        await svc.require_autopilot_admin(db, ap, user)
        await svc.remove_collaborator(db, ap, user_id)
    except svc.AutomationError as e:
        raise _http(e)


# ── Subscribers (multica 120) ─────────────────────────────────────────
@router.get("/{autopilot_id}/subscribers")
async def list_subscribers(autopilot_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.get_autopilot(db, autopilot_id)
    except svc.AutomationError as e:
        raise _http(e)
    return await svc.list_autopilot_subscribers(db, autopilot_id)


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
            created_by_type="member",
            created_by_id=user.id,
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
        ap = await _load_writable(db, autopilot_id, user)
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
        ap = await _load_writable(db, autopilot_id, user)
        await svc.update_autopilot(
            db, autopilot_id, {"enabled": not ap.enabled}, actor_type="member", actor_id=user.id
        )
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
        await _load_writable(db, autopilot_id, user)
        await svc.delete_autopilot(db, autopilot_id)
    except svc.AutomationError as e:
        raise _http(e)
    ctx = await _autopilots_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/_autopilots_list.html", ctx)
