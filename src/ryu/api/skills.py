"""API + páginas do domínio SKILLS.

- `router`: rotas JSON, montar em main.py com prefix="/api/skills".
- `pages_router`: páginas HTML (/w/{slug}/skills), montar SEM prefixo.
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


class SkillCreate(BaseModel):
    workspace_id: str
    name: str
    description: str = ""
    content: str = ""


class SkillPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    content: str | None = None


# ── JSON API ──────────────────────────────────────────────────────────
@router.post("", status_code=201)
async def create_skill(payload: SkillCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        skill = await svc.create_skill(db, payload.workspace_id, payload.name, payload.description, payload.content)
    except svc.AutomationError as e:
        raise _http(e)
    return svc.skill_to_dict(skill)


@router.get("")
async def list_skills(workspace_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    return [svc.skill_to_dict(s) for s in await svc.list_skills(db, workspace_id)]


@router.get("/agent/{agent_id}")
async def skills_of_agent(agent_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    return [svc.skill_to_dict(s) for s in await svc.skills_for_agent(db, agent_id)]


@router.get("/{skill_id}")
async def get_skill(skill_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        skill = await svc.get_skill(db, skill_id)
    except svc.AutomationError as e:
        raise _http(e)
    agents = await svc.agents_for_skill(db, skill_id)
    d = svc.skill_to_dict(skill)
    d["agents"] = [{"id": a.id, "name": a.name, "handle": a.handle} for a in agents]
    return d


@router.patch("/{skill_id}")
async def patch_skill(skill_id: str, payload: SkillPatch, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        skill = await svc.update_skill(db, skill_id, payload.model_dump(exclude_unset=True))
    except svc.AutomationError as e:
        raise _http(e)
    return svc.skill_to_dict(skill)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.delete_skill(db, skill_id)
    except svc.AutomationError as e:
        raise _http(e)


@router.post("/{skill_id}/agents/{agent_id}", status_code=204)
async def attach(skill_id: str, agent_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.attach_skill(db, skill_id, agent_id)
    except svc.AutomationError as e:
        raise _http(e)


@router.delete("/{skill_id}/agents/{agent_id}", status_code=204)
async def detach(skill_id: str, agent_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await svc.detach_skill(db, skill_id, agent_id)


# ── Páginas HTML ──────────────────────────────────────────────────────
async def _workspace_by_slug(db: AsyncSession, slug: str) -> Workspace:
    row = await db.execute(select(Workspace).where(Workspace.slug == slug))
    ws = row.scalar_one_or_none()
    if ws is None:
        raise HTTPException(404, "workspace não encontrado")
    return ws


async def _skills_ctx(db: AsyncSession, ws: Workspace) -> dict:
    skills = await svc.list_skills(db, ws.id)
    agents = list((await db.execute(select(Agent).where(Agent.workspace_id == ws.id))).scalars())
    attached: dict[str, list[Agent]] = {}
    for s in skills:
        attached[s.id] = await svc.agents_for_skill(db, s.id)
    return {"workspace": ws, "skills": skills, "agents": agents, "attached": attached}


@pages_router.get("/w/{slug}/skills", response_class=HTMLResponse)
async def skills_page(slug: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    ws = await _workspace_by_slug(db, slug)
    ctx = await _skills_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/skills.html", ctx)


@pages_router.post("/w/{slug}/skills", response_class=HTMLResponse)
async def skills_page_create(
    slug: str,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    content: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    try:
        await svc.create_skill(db, ws.id, name, description, content)
    except svc.AutomationError as e:
        raise _http(e)
    ctx = await _skills_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/_skills_list.html", ctx)


@pages_router.post("/w/{slug}/skills/{skill_id}/attach", response_class=HTMLResponse)
async def skills_page_attach(
    slug: str,
    skill_id: str,
    request: Request,
    agent_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    try:
        await svc.attach_skill(db, skill_id, agent_id)
    except svc.AutomationError as e:
        raise _http(e)
    ctx = await _skills_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/_skills_list.html", ctx)


@pages_router.post("/w/{slug}/skills/{skill_id}/detach/{agent_id}", response_class=HTMLResponse)
async def skills_page_detach(
    slug: str,
    skill_id: str,
    agent_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    await svc.detach_skill(db, skill_id, agent_id)
    ctx = await _skills_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/_skills_list.html", ctx)


@pages_router.post("/w/{slug}/skills/{skill_id}/delete", response_class=HTMLResponse)
async def skills_page_delete(
    slug: str,
    skill_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    try:
        await svc.delete_skill(db, skill_id)
    except svc.AutomationError as e:
        raise _http(e)
    ctx = await _skills_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/_skills_list.html", ctx)
