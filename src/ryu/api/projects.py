"""API + páginas do domínio PROJECTS.

- `router`: rotas JSON, montar em main.py com prefix="/api/projects".
- `pages_router`: páginas HTML (/w/{slug}/projects, /w/{slug}/projects/{project_id}), montar SEM prefixo.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import get_db
from ryu.models import Issue, Project, User
from ryu.realtime.hub import hub
from ryu.services import issues as issues_svc
from ryu.services.auth import current_user, current_workspace

router = APIRouter()
pages_router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

PROJECT_STATUSES = ["active", "archived"]


def project_to_dict(p: Project, issue_count: int | None = None) -> dict:
    d = {
        "id": p.id,
        "workspace_id": p.workspace_id,
        "name": p.name,
        "description": p.description,
        "status": p.status,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }
    if issue_count is not None:
        d["issue_count"] = issue_count
    return d


async def _get_project(db: AsyncSession, project_id: str) -> Project:
    p = await db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "project não encontrado")
    return p


# ── Schemas ───────────────────────────────────────────────────────────
class ProjectCreate(BaseModel):
    workspace_id: str
    name: str
    description: str = ""
    status: str = "active"


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


# ── API JSON ──────────────────────────────────────────────────────────
@router.post("", status_code=201)
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    if not payload.name.strip():
        raise HTTPException(400, "name é obrigatório")
    if payload.status not in PROJECT_STATUSES:
        raise HTTPException(400, f"status inválido: {payload.status}")
    project = Project(
        workspace_id=payload.workspace_id,
        name=payload.name.strip(),
        description=payload.description or "",
        status=payload.status,
    )
    db.add(project)
    await db.commit()
    await hub.publish(project.workspace_id, "project:created", project_to_dict(project))
    return project_to_dict(project)


@router.get("")
async def list_projects(workspace_id: str, status: str | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Project).where(Project.workspace_id == workspace_id)
    if status:
        stmt = stmt.where(Project.status == status)
    rows = await db.execute(stmt.order_by(Project.created_at))
    return [project_to_dict(p) for p in rows.scalars()]


@router.get("/{project_id}")
async def get_project(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    p = await _get_project(db, project_id)
    row = await db.execute(select(func.count(Issue.id)).where(Issue.project_id == p.id))
    return project_to_dict(p, issue_count=row.scalar_one())


@router.get("/{project_id}/issues")
async def project_issues(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    p = await _get_project(db, project_id)
    items = await issues_svc.list_issues(db, p.workspace_id, project_id=p.id)
    return [issues_svc.issue_to_dict(i) for i in items]


@router.patch("/{project_id}")
async def update_project(project_id: str, payload: ProjectUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    p = await _get_project(db, project_id)
    if payload.name is not None:
        if not payload.name.strip():
            raise HTTPException(400, "name não pode ser vazio")
        p.name = payload.name.strip()
    if payload.description is not None:
        p.description = payload.description
    if payload.status is not None:
        if payload.status not in PROJECT_STATUSES:
            raise HTTPException(400, f"status inválido: {payload.status}")
        p.status = payload.status
    await db.commit()
    await hub.publish(p.workspace_id, "project:updated", project_to_dict(p))
    return project_to_dict(p)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    p = await _get_project(db, project_id)
    ws_id = p.workspace_id
    await db.execute(update(Issue).where(Issue.project_id == p.id).values(project_id=None))
    await db.delete(p)
    await db.commit()
    await hub.publish(ws_id, "project:deleted", {"id": project_id})
    return Response(status_code=204)


# ── Páginas HTML ──────────────────────────────────────────────────────
@pages_router.get("/w/{slug}/projects", response_class=HTMLResponse)
async def projects_page(slug: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    ws = await current_workspace(slug, db, user)
    rows = await db.execute(select(Project).where(Project.workspace_id == ws.id).order_by(Project.created_at))
    projects = list(rows.scalars())
    counts_rows = await db.execute(
        select(Issue.project_id, func.count(Issue.id))
        .where(Issue.workspace_id == ws.id, Issue.project_id.is_not(None))
        .group_by(Issue.project_id)
    )
    issue_counts = {pid: n for pid, n in counts_rows.all()}
    return templates.TemplateResponse(
        "projects/index.html",
        {"request": request, "user": user, "workspace": ws, "active_nav": "projects",
         "projects": projects, "issue_counts": issue_counts},
    )


@pages_router.post("/w/{slug}/projects", response_class=HTMLResponse)
async def projects_page_create(
    slug: str,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await current_workspace(slug, db, user)
    if name.strip():
        project = Project(workspace_id=ws.id, name=name.strip(), description=description or "")
        db.add(project)
        await db.commit()
        await hub.publish(ws.id, "project:created", project_to_dict(project))
    return RedirectResponse(f"/w/{slug}/projects", status_code=303)


@pages_router.get("/w/{slug}/projects/{project_id}", response_class=HTMLResponse)
async def project_detail_page(slug: str, project_id: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    ws = await current_workspace(slug, db, user)
    p = await _get_project(db, project_id)
    if p.workspace_id != ws.id:
        raise HTTPException(404, "project não encontrado")
    issues = await issues_svc.list_issues(db, ws.id, project_id=p.id)
    return templates.TemplateResponse(
        "projects/detail.html",
        {"request": request, "user": user, "workspace": ws, "active_nav": "projects",
         "project": p, "issues": issues,
         "status_titles": {
             "backlog": "Backlog", "todo": "Todo", "in_progress": "In Progress",
             "in_review": "In Review", "done": "Done", "blocked": "Blocked", "cancelled": "Cancelled",
         }},
    )
