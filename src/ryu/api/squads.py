"""API + páginas do domínio SQUADS.

- `router`: rotas JSON, montar em main.py com prefix="/api/squads".
- `pages_router`: páginas HTML (/w/{slug}/squads), montar SEM prefixo.
Atribuir issue a squad = task de briefing (queued) para o leader_agent_id,
que delega via API usando seu token rat_.
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
from ryu.models import Agent, Issue, User, Workspace
from ryu.services import automation as svc
from ryu.services.auth import current_user

router = APIRouter()
pages_router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _http(e: svc.AutomationError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=e.message)


class SquadCreate(BaseModel):
    workspace_id: str
    name: str
    leader_agent_id: str
    description: str = ""
    instructions: str = ""


class SquadPatch(BaseModel):
    name: str | None = None
    leader_agent_id: str | None = None
    description: str | None = None
    instructions: str | None = None


class MemberAdd(BaseModel):
    member_type: str  # agent|member
    member_id: str
    role: str = ""


class MemberRolePatch(BaseModel):
    member_id: str
    member_type: str = "agent"
    role: str


class AssignIssue(BaseModel):
    issue_id: str


# ── JSON API ──────────────────────────────────────────────────────────
@router.post("", status_code=201)
async def create_squad(payload: SquadCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        squad = await svc.create_squad(
            db, payload.workspace_id, payload.name, payload.leader_agent_id,
            description=payload.description, instructions=payload.instructions,
        )
    except svc.AutomationError as e:
        raise _http(e)
    return svc.squad_to_dict(squad, await svc.list_squad_members(db, squad.id))


@router.get("")
async def list_squads(workspace_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    out = []
    for s in await svc.list_squads(db, workspace_id):
        out.append(svc.squad_to_dict(s, await svc.list_squad_members(db, s.id)))
    return out


@router.get("/{squad_id}")
async def get_squad(squad_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        squad = await svc.get_squad(db, squad_id)
    except svc.AutomationError as e:
        raise _http(e)
    return svc.squad_to_dict(squad, await svc.list_squad_members(db, squad_id))


@router.patch("/{squad_id}")
async def patch_squad(squad_id: str, payload: SquadPatch, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        squad = await svc.update_squad(db, squad_id, payload.model_dump(exclude_unset=True))
    except svc.AutomationError as e:
        raise _http(e)
    return svc.squad_to_dict(squad, await svc.list_squad_members(db, squad_id))


@router.delete("/{squad_id}", status_code=204)
async def delete_squad(squad_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.delete_squad(db, squad_id)
    except svc.AutomationError as e:
        raise _http(e)


@router.get("/{squad_id}/members")
async def members(squad_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.get_squad(db, squad_id)
    except svc.AutomationError as e:
        raise _http(e)
    return [
        {"member_type": m.member_type, "member_id": m.member_id, "role": getattr(m, "role", "") or ""}
        for m in await svc.list_squad_members(db, squad_id)
    ]


@router.get("/{squad_id}/members/status")
async def members_status(squad_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    """Status derivado dos membros (working/idle/archived + issues ativas)."""
    try:
        return await svc.list_squad_member_status(db, squad_id)
    except svc.AutomationError as e:
        raise _http(e)


@router.patch("/{squad_id}/members/role")
async def patch_member_role(
    squad_id: str, payload: MemberRolePatch, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        row = await svc.set_squad_member_role(
            db, squad_id, payload.member_type, payload.member_id, payload.role
        )
    except svc.AutomationError as e:
        raise _http(e)
    return {"member_type": row.member_type, "member_id": row.member_id, "role": row.role}


@router.post("/{squad_id}/members", status_code=204)
async def add_member(squad_id: str, payload: MemberAdd, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.add_squad_member(db, squad_id, payload.member_type, payload.member_id, payload.role)
    except svc.AutomationError as e:
        raise _http(e)


@router.delete("/{squad_id}/members/{member_type}/{member_id}", status_code=204)
async def remove_member(
    squad_id: str, member_type: str, member_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    await svc.remove_squad_member(db, squad_id, member_type, member_id)


@router.post("/{squad_id}/assign-issue")
async def assign_issue(
    squad_id: str, payload: AssignIssue, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        task = await svc.assign_issue_to_squad(db, squad_id, payload.issue_id, "member", user.id)
    except svc.AutomationError as e:
        raise _http(e)
    return {"task_id": task.id, "agent_id": task.agent_id, "issue_id": task.issue_id, "status": task.status}


# ── Páginas HTML ──────────────────────────────────────────────────────
async def _workspace_by_slug(db: AsyncSession, slug: str) -> Workspace:
    row = await db.execute(select(Workspace).where(Workspace.slug == slug))
    ws = row.scalar_one_or_none()
    if ws is None:
        raise HTTPException(404, "workspace não encontrado")
    return ws


async def _squads_ctx(db: AsyncSession, ws: Workspace) -> dict:
    squads = await svc.list_squads(db, ws.id)
    agents = list((await db.execute(select(Agent).where(Agent.workspace_id == ws.id))).scalars())
    agent_names = {a.id: a.name for a in agents}
    squad_members = {s.id: await svc.list_squad_members(db, s.id) for s in squads}
    issues = list(
        (
            await db.execute(
                select(Issue).where(
                    Issue.workspace_id == ws.id,
                    Issue.status.in_(["backlog", "todo", "in_progress", "blocked"]),
                )
            )
        ).scalars()
    )
    return {
        "workspace": ws,
        "squads": squads,
        "agents": agents,
        "agent_names": agent_names,
        "squad_members": squad_members,
        "issues": issues,
    }


@pages_router.get("/w/{slug}/squads", response_class=HTMLResponse)
async def squads_page(slug: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    ws = await _workspace_by_slug(db, slug)
    ctx = await _squads_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/squads.html", ctx)


@pages_router.post("/w/{slug}/squads", response_class=HTMLResponse)
async def squads_page_create(
    slug: str,
    request: Request,
    name: str = Form(...),
    leader_agent_id: str = Form(...),
    description: str = Form(""),
    instructions: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    try:
        await svc.create_squad(
            db, ws.id, name, leader_agent_id, description=description, instructions=instructions
        )
    except svc.AutomationError as e:
        raise _http(e)
    ctx = await _squads_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/_squads_list.html", ctx)


@pages_router.post("/w/{slug}/squads/{squad_id}/members", response_class=HTMLResponse)
async def squads_page_add_member(
    slug: str,
    squad_id: str,
    request: Request,
    agent_id: str = Form(...),
    role: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    try:
        await svc.add_squad_member(db, squad_id, "agent", agent_id, role)
    except svc.AutomationError as e:
        raise _http(e)
    ctx = await _squads_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/_squads_list.html", ctx)


@pages_router.post("/w/{slug}/squads/{squad_id}/assign", response_class=HTMLResponse)
async def squads_page_assign(
    slug: str,
    squad_id: str,
    request: Request,
    issue_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    try:
        await svc.assign_issue_to_squad(db, squad_id, issue_id, "member", user.id)
    except svc.AutomationError as e:
        raise _http(e)
    ctx = await _squads_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/_squads_list.html", ctx)


@pages_router.post("/w/{slug}/squads/{squad_id}/update", response_class=HTMLResponse)
async def squads_page_update(
    slug: str,
    squad_id: str,
    request: Request,
    description: str = Form(""),
    instructions: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    try:
        await svc.update_squad(db, squad_id, {"description": description, "instructions": instructions})
    except svc.AutomationError as e:
        raise _http(e)
    ctx = await _squads_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/_squads_list.html", ctx)


@pages_router.post("/w/{slug}/squads/{squad_id}/delete", response_class=HTMLResponse)
async def squads_page_delete(
    slug: str,
    squad_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    try:
        await svc.delete_squad(db, squad_id)
    except svc.AutomationError as e:
        raise _http(e)
    ctx = await _squads_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/_squads_list.html", ctx)
