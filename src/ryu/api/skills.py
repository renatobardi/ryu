"""API + páginas do domínio SKILLS.

- `router`: rotas JSON, montar em main.py com prefix="/api/skills".
  Inclui skill files, labels, import (.md/.zip) e descoberta/import de
  skills locais do runtime in-process (equivalente multica local-skills).
- `pages_router`: páginas HTML (/w/{slug}/skills), montar SEM prefixo.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import get_db
from ryu.models import Agent, User, Workspace
from ryu.services import skills as svc
from ryu.services.automation import AutomationError
from ryu.services.auth import current_user

router = APIRouter()
pages_router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _http(e: AutomationError) -> HTTPException:
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


class SkillFilePut(BaseModel):
    path: str
    content: str = ""


class SkillLabelAttach(BaseModel):
    label_id: str | None = None
    name: str | None = None
    color: str | None = None


class LocalSkillImport(BaseModel):
    workspace_id: str
    dir_name: str
    on_conflict: str = "fail"  # fail|overwrite|rename|skip


# ── JSON API ──────────────────────────────────────────────────────────
@router.post("", status_code=201)
async def create_skill(payload: SkillCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        skill = await svc.create_skill(
            db, payload.workspace_id, payload.name, payload.description, payload.content,
            created_by=user.id,
        )
    except AutomationError as e:
        raise _http(e)
    return svc.skill_to_dict(skill)


@router.get("")
async def list_skills(
    workspace_id: str,
    label_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    return [svc.skill_to_dict(s) for s in await svc.list_skills(db, workspace_id, label_id=label_id)]


@router.get("/agent/{agent_id}")
async def skills_of_agent(agent_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    return [svc.skill_to_dict(s) for s in await svc.skills_for_agent(db, agent_id)]


# ── Import (.md único ou .zip com SKILL.md + arquivos) ────────────────
@router.post("/import", status_code=201)
async def import_skill(
    workspace_id: str = Form(...),
    on_conflict: str = Form("fail"),  # fail|overwrite|rename|skip
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "arquivo excede 10MB")
    try:
        result = await svc.import_skill(
            db,
            workspace_id,
            filename=file.filename or "",
            data=data,
            on_conflict=on_conflict,
            created_by=user.id,
        )
    except AutomationError as e:
        raise _http(e)
    return result


# ── Skills locais do runtime in-process (multica runtime local-skills) ─
@router.get("/local-runtime")
async def list_local_skills(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    """Varre o diretório de skills do runtime local (RYU_LOCAL_SKILLS_DIR
    ou ~/.claude/skills). Equivalente síncrono do request assíncrono
    POST/GET /api/runtimes/{id}/local-skills do multica."""
    return svc.scan_local_skills()


@router.post("/local-runtime/import", status_code=201)
async def import_local_skill(
    payload: LocalSkillImport, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        result = await svc.import_local_skill(
            db,
            payload.workspace_id,
            payload.dir_name,
            on_conflict=payload.on_conflict,
            created_by=user.id,
        )
    except AutomationError as e:
        raise _http(e)
    return result


@router.get("/{skill_id}")
async def get_skill(skill_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        skill = await svc.get_skill(db, skill_id)
    except AutomationError as e:
        raise _http(e)
    agents = await svc.agents_for_skill(db, skill_id)
    d = svc.skill_to_dict(skill)
    d["agents"] = [{"id": a.id, "name": a.name, "handle": a.handle} for a in agents]
    return d


@router.patch("/{skill_id}")
async def patch_skill(skill_id: str, payload: SkillPatch, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        skill = await svc.update_skill(db, skill_id, payload.model_dump(exclude_unset=True))
    except AutomationError as e:
        raise _http(e)
    return svc.skill_to_dict(skill)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.delete_skill(db, skill_id)
    except AutomationError as e:
        raise _http(e)


@router.post("/{skill_id}/agents/{agent_id}", status_code=204)
async def attach(skill_id: str, agent_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.attach_skill(db, skill_id, agent_id)
    except AutomationError as e:
        raise _http(e)


@router.delete("/{skill_id}/agents/{agent_id}", status_code=204)
async def detach(skill_id: str, agent_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await svc.detach_skill(db, skill_id, agent_id)


# ── Skill files (multica skill_file) ──────────────────────────────────
@router.get("/{skill_id}/files")
async def list_files(skill_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        return [svc.skill_file_to_dict(f) for f in await svc.list_skill_files(db, skill_id)]
    except AutomationError as e:
        raise _http(e)


@router.put("/{skill_id}/files")
async def upsert_file(
    skill_id: str, payload: SkillFilePut, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        f = await svc.upsert_skill_file(db, skill_id, payload.path, payload.content)
    except AutomationError as e:
        raise _http(e)
    return svc.skill_file_to_dict(f)


@router.delete("/{skill_id}/files/{file_id}", status_code=204)
async def delete_file(
    skill_id: str, file_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        await svc.delete_skill_file(db, skill_id, file_id)
    except AutomationError as e:
        raise _http(e)


# ── Skill labels (multica resource_labels) ────────────────────────────
@router.get("/{skill_id}/labels")
async def list_labels(skill_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        return [svc.label_to_dict(lb) for lb in await svc.list_labels_for_skill(db, skill_id)]
    except AutomationError as e:
        raise _http(e)


@router.post("/{skill_id}/labels", status_code=201)
async def attach_label(
    skill_id: str, payload: SkillLabelAttach, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        lb = await svc.attach_label_to_skill(
            db, skill_id, label_id=payload.label_id, name=payload.name, color=payload.color
        )
    except AutomationError as e:
        raise _http(e)
    return svc.label_to_dict(lb)


@router.delete("/{skill_id}/labels/{label_id}", status_code=204)
async def detach_label(
    skill_id: str, label_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        await svc.get_skill(db, skill_id)
    except AutomationError as e:
        raise _http(e)
    await svc.detach_label_from_skill(db, skill_id, label_id)


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
    except AutomationError as e:
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
    except AutomationError as e:
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
    except AutomationError as e:
        raise _http(e)
    ctx = await _skills_ctx(db, ws)
    ctx["request"] = request
    return templates.TemplateResponse("automation/_skills_list.html", ctx)
