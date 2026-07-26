"""API + páginas do domínio ISSUES/TRACKER.

- `router`: rotas JSON, montar em main.py com prefix="/api/issues".
- `pages_router`: páginas HTML (/w/{slug}/board, /w/{slug}/issues/{key}), montar SEM prefixo.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import get_db
from ryu.models import Agent, Issue, User, Workspace
from ryu.services import issues as svc
from ryu.services.auth import current_user

router = APIRouter()
pages_router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

BOARD_COLUMNS = ["backlog", "todo", "in_progress", "in_review", "done", "blocked"]
STATUS_TITLES = {
    "backlog": "Backlog",
    "todo": "Todo",
    "in_progress": "In Progress",
    "in_review": "In Review",
    "done": "Done",
    "blocked": "Blocked",
    "cancelled": "Cancelled",
}


def _err(e: svc.IssueError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=e.message)


# ── Schemas ───────────────────────────────────────────────────────────
class IssueCreate(BaseModel):
    workspace_id: str
    title: str
    description: str = ""
    status: str = "backlog"
    priority: str = "none"
    assignee_type: str | None = None
    assignee_id: str | None = None
    parent_issue_id: str | None = None
    project_id: str | None = None
    label_ids: list[str] | None = None


class IssueUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    assignee_type: str | None = None
    assignee_id: str | None = None
    parent_issue_id: str | None = None
    project_id: str | None = None
    position: float | None = None
    due_date: datetime | None = None
    # marca quais campos vieram no payload (model_fields_set)


class IssueMove(BaseModel):
    status: str
    before_id: str | None = None  # card logo abaixo do destino
    after_id: str | None = None  # card logo acima do destino


class MetaPatch(BaseModel):
    key: str
    value: Any = None


class LabelCreate(BaseModel):
    workspace_id: str
    name: str
    color: str = "#8b5cf6"


class LabelUpdate(BaseModel):
    name: str | None = None
    color: str | None = None


class CommentCreate(BaseModel):
    body: str
    parent_comment_id: str | None = None


class CommentUpdate(BaseModel):
    body: str


# ── Labels ────────────────────────────────────────────────────────────
@router.post("/labels", status_code=201)
async def create_label(payload: LabelCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        label = await svc.create_label(db, payload.workspace_id, "member", user.id, payload.name, payload.color)
    except svc.IssueError as e:
        raise _err(e)
    return svc.label_to_dict(label)


@router.get("/labels")
async def list_labels(workspace_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    return [svc.label_to_dict(lb) for lb in await svc.list_labels(db, workspace_id)]


@router.patch("/labels/{label_id}")
async def update_label(label_id: str, payload: LabelUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        label = await svc.update_label(db, label_id, "member", user.id, payload.name, payload.color)
    except svc.IssueError as e:
        raise _err(e)
    return svc.label_to_dict(label)


@router.delete("/labels/{label_id}", status_code=204)
async def delete_label(label_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.delete_label(db, label_id, "member", user.id)
    except svc.IssueError as e:
        raise _err(e)
    return Response(status_code=204)


@router.post("/{issue_id}/labels/{label_id}", status_code=204)
async def attach_label(issue_id: str, label_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.attach_label(db, issue_id, label_id, "member", user.id)
    except svc.IssueError as e:
        raise _err(e)
    return Response(status_code=204)


@router.delete("/{issue_id}/labels/{label_id}", status_code=204)
async def detach_label(issue_id: str, label_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.detach_label(db, issue_id, label_id, "member", user.id)
    except svc.IssueError as e:
        raise _err(e)
    return Response(status_code=204)


# ── Issues ────────────────────────────────────────────────────────────
@router.post("", status_code=201)
async def create_issue(
    payload: IssueCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        issue = await svc.create_issue(
            db,
            payload.workspace_id,
            "member",
            user.id,
            title=payload.title,
            description=payload.description,
            status=payload.status,
            priority=payload.priority,
            assignee_type=payload.assignee_type,
            assignee_id=payload.assignee_id,
            parent_issue_id=payload.parent_issue_id,
            project_id=payload.project_id,
            label_ids=payload.label_ids,
        )
    except svc.IssueError as e:
        raise _err(e)
    return svc.issue_to_dict(issue, await svc.issue_labels(db, issue.id))


@router.get("")
async def list_issues(
    workspace_id: str,
    status: str | None = None,
    assignee_type: str | None = None,
    assignee_id: str | None = None,
    label_id: str | None = None,
    parent_issue_id: str | None = None,
    project_id: str | None = None,
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    items = await svc.list_issues(
        db,
        workspace_id,
        status=status,
        assignee_type=assignee_type,
        assignee_id=assignee_id,
        label_id=label_id,
        parent_issue_id=parent_issue_id,
        project_id=project_id,
        q=q,
    )
    return [svc.issue_to_dict(i) for i in items]


@router.get("/{issue_id}")
async def get_issue(issue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        issue = await svc.get_issue(db, issue_id)
    except svc.IssueError as e:
        raise _err(e)
    d = svc.issue_to_dict(issue, await svc.issue_labels(db, issue.id))
    subs = await svc.list_issues(db, issue.workspace_id, parent_issue_id=issue.id)
    d["sub_issues"] = [svc.issue_to_dict(s) for s in subs]
    return d


@router.patch("/{issue_id}")
async def update_issue(
    issue_id: str,
    payload: IssueUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    changes = {k: getattr(payload, k) for k in payload.model_fields_set}
    try:
        issue = await svc.update_issue(db, issue_id, "member", user.id, changes)
    except svc.IssueError as e:
        raise _err(e)
    return svc.issue_to_dict(issue, await svc.issue_labels(db, issue.id))


@router.post("/{issue_id}/move")
async def move_issue(
    issue_id: str,
    payload: IssueMove,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        issue = await svc.move_issue(
            db, issue_id, "member", user.id,
            status=payload.status, before_id=payload.before_id, after_id=payload.after_id,
        )
    except svc.IssueError as e:
        raise _err(e)
    return svc.issue_to_dict(issue)


@router.delete("/{issue_id}", status_code=204)
async def delete_issue(issue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.delete_issue(db, issue_id, "member", user.id)
    except svc.IssueError as e:
        raise _err(e)
    return Response(status_code=204)


# ── Meta KV ───────────────────────────────────────────────────────────
@router.patch("/{issue_id}/meta")
async def patch_meta(
    issue_id: str,
    payload: MetaPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        meta = await svc.set_issue_meta(db, issue_id, "member", user.id, payload.key, payload.value)
    except svc.IssueError as e:
        raise _err(e)
    return {"meta": meta}


# ── Sub-issues ────────────────────────────────────────────────────────
@router.get("/{issue_id}/sub-issues")
async def sub_issues(issue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        issue = await svc.get_issue(db, issue_id)
    except svc.IssueError as e:
        raise _err(e)
    subs = await svc.list_issues(db, issue.workspace_id, parent_issue_id=issue.id)
    return [svc.issue_to_dict(s) for s in subs]


# ── Comentários ───────────────────────────────────────────────────────
@router.post("/{issue_id}/comments", status_code=201)
async def create_comment(
    issue_id: str,
    payload: CommentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        comment = await svc.create_comment(db, issue_id, "member", user.id, payload.body, payload.parent_comment_id)
    except svc.IssueError as e:
        raise _err(e)
    return svc.comment_to_dict(comment)


@router.get("/{issue_id}/comments")
async def list_comments(issue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    return [svc.comment_to_dict(c) for c in await svc.list_comments(db, issue_id)]


@router.patch("/comments/{comment_id}")
async def update_comment(comment_id: str, payload: CommentUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        comment = await svc.update_comment(db, comment_id, "member", user.id, payload.body)
    except svc.IssueError as e:
        raise _err(e)
    return svc.comment_to_dict(comment)


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(comment_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.delete_comment(db, comment_id, "member", user.id)
    except svc.IssueError as e:
        raise _err(e)
    return Response(status_code=204)


# ── Activity ──────────────────────────────────────────────────────────
@router.get("/{issue_id}/activity")
async def issue_activity(issue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    rows = await svc.list_activity(db, issue_id)
    return [
        {
            "id": a.id,
            "actor_type": a.actor_type,
            "actor_id": a.actor_id,
            "action": a.action,
            "payload": a.payload,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]


# ── Páginas HTML (HTMX) ───────────────────────────────────────────────
async def _workspace_by_slug(db: AsyncSession, slug: str) -> Workspace:
    row = await db.execute(select(Workspace).where(Workspace.slug == slug))
    ws = row.scalar_one_or_none()
    if ws is None:
        raise HTTPException(404, "workspace não encontrado")
    return ws


async def _board_ctx(db: AsyncSession, ws: Workspace) -> dict:
    items = await svc.list_issues(db, ws.id)
    columns = {st: [] for st in BOARD_COLUMNS}
    for i in items:
        columns.setdefault(i.status, []).append(i)
    agents = list((await db.execute(select(Agent).where(Agent.workspace_id == ws.id))).scalars())
    agent_names = {a.id: a.name for a in agents}
    return {
        "workspace": ws,
        "columns": columns,
        "column_order": BOARD_COLUMNS,
        "status_titles": STATUS_TITLES,
        "agents": agents,
        "agent_names": agent_names,
    }


@pages_router.get("/w/{slug}/board", response_class=HTMLResponse)
async def board_page(slug: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    ws = await _workspace_by_slug(db, slug)
    ctx = await _board_ctx(db, ws)
    ctx["request"] = request
    ctx["user"] = user
    return templates.TemplateResponse("issues/board.html", ctx)


@pages_router.post("/w/{slug}/board/move", response_class=HTMLResponse)
async def board_move(
    slug: str,
    request: Request,
    issue_id: str = Form(...),
    status: str = Form(...),
    before_id: str | None = Form(None),
    after_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    try:
        await svc.move_issue(db, issue_id, "member", user.id, status=status, before_id=before_id or None, after_id=after_id or None)
    except svc.IssueError as e:
        raise _err(e)
    ctx = await _board_ctx(db, ws)
    ctx["request"] = request
    ctx["user"] = user
    return templates.TemplateResponse("issues/_board_columns.html", ctx)


@pages_router.post("/w/{slug}/board/issues", response_class=HTMLResponse)
async def board_create_issue(
    slug: str,
    request: Request,
    title: str = Form(...),
    status: str = Form("backlog"),
    priority: str = Form("none"),
    assignee_agent_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    at, aid = (("agent", assignee_agent_id) if assignee_agent_id else (None, None))
    try:
        await svc.create_issue(db, ws.id, "member", user.id, title=title, status=status, priority=priority, assignee_type=at, assignee_id=aid)
    except svc.IssueError as e:
        raise _err(e)
    ctx = await _board_ctx(db, ws)
    ctx["request"] = request
    ctx["user"] = user
    return templates.TemplateResponse("issues/_board_columns.html", ctx)


@pages_router.get("/w/{slug}/issues/{key}", response_class=HTMLResponse)
async def issue_page(slug: str, key: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    ws = await _workspace_by_slug(db, slug)
    row = await db.execute(select(Issue).where(Issue.workspace_id == ws.id, Issue.key == key))
    issue = row.scalar_one_or_none()
    if issue is None:
        raise HTTPException(404, "issue não encontrada")
    labels = await svc.issue_labels(db, issue.id)
    comments = await svc.list_comments(db, issue.id)
    subs = await svc.list_issues(db, ws.id, parent_issue_id=issue.id)
    activity = await svc.list_activity(db, issue.id, limit=50)
    agents = list((await db.execute(select(Agent).where(Agent.workspace_id == ws.id))).scalars())
    agent_names = {a.id: a.name for a in agents}
    return templates.TemplateResponse(
        "issues/detail.html",
        {
            "request": request,
            "user": user,
            "workspace": ws,
            "issue": issue,
            "labels": labels,
            "comments": comments,
            "sub_issues": subs,
            "activity": activity,
            "agents": agents,
            "agent_names": agent_names,
            "statuses": svc.ISSUE_STATUSES,
            "priorities": svc.PRIORITIES,
            "status_titles": STATUS_TITLES,
        },
    )


@pages_router.post("/w/{slug}/issues/{key}/comments", response_class=HTMLResponse)
async def issue_page_comment(
    slug: str,
    key: str,
    request: Request,
    body: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    row = await db.execute(select(Issue).where(Issue.workspace_id == ws.id, Issue.key == key))
    issue = row.scalar_one_or_none()
    if issue is None:
        raise HTTPException(404, "issue não encontrada")
    try:
        await svc.create_comment(db, issue.id, "member", user.id, body)
    except svc.IssueError as e:
        raise _err(e)
    comments = await svc.list_comments(db, issue.id)
    return templates.TemplateResponse(
        "issues/_comments.html",
        {"request": request, "user": user, "workspace": ws, "issue": issue, "comments": comments},
    )
