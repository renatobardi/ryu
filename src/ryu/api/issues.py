"""API + páginas do domínio ISSUES/TRACKER.

- `router`: rotas JSON, montar em main.py com prefix="/api/issues".
- `pages_router`: páginas HTML (/w/{slug}/board, /w/{slug}/issues/{key}), montar SEM prefixo.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
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


def _actor(user: User) -> tuple[str, str]:
    """Ator polimórfico: tokens rat_/rdt_ representam agentes (user.id = 'agent:<id>')."""
    if user.id.startswith("agent:"):
        return "agent", user.id.split(":", 1)[1]
    return "member", user.id


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


class IssueQuery(BaseModel):
    """Filtros da listagem (POST /query aceita conjuntos grandes de ids)."""

    workspace_id: str
    ids: list[str] | None = None
    statuses: list[str] | None = None
    priorities: list[str] | None = None
    assignee_ids: list[str] | None = None
    assignee_type: str | None = None
    creator_id: str | None = None
    creator_type: str | None = None
    involves_user_id: str | None = None
    project_ids: list[str] | None = None
    include_no_project: bool = False
    label_ids: list[str] | None = None
    parent_issue_id: str | None = None
    metadata: dict | None = None
    properties: dict | None = None
    top_level_only: bool = False
    open_only: bool = False
    scheduled: bool = False
    q: str | None = None
    sort: str | None = None
    direction: str | None = None
    limit: int | None = None
    offset: int = 0

    def filters(self) -> dict:
        return {
            "ids": self.ids,
            "statuses": self.statuses,
            "priorities": self.priorities,
            "assignee_ids": self.assignee_ids,
            "assignee_type": self.assignee_type,
            "creator_id": self.creator_id,
            "creator_type": self.creator_type,
            "involves_user_id": self.involves_user_id,
            "project_ids": self.project_ids,
            "include_no_project": self.include_no_project,
            "label_ids": self.label_ids,
            "parent_issue_id": self.parent_issue_id,
            "metadata": self.metadata,
            "properties": self.properties,
            "top_level_only": self.top_level_only,
            "open_only": self.open_only,
            "scheduled": self.scheduled,
            "q": self.q,
        }


class BatchUpdate(BaseModel):
    workspace_id: str
    issue_ids: list[str]
    status: str | None = None
    priority: str | None = None
    assignee_type: str | None = None
    assignee_id: str | None = None
    project_id: str | None = None
    due_date: datetime | None = None
    add_label_ids: list[str] | None = None
    remove_label_ids: list[str] | None = None


class BatchDelete(BaseModel):
    workspace_id: str
    issue_ids: list[str]


class SubscribePayload(BaseModel):
    user_type: str | None = None  # default: ator atual
    user_id: str | None = None


class ReactionPayload(BaseModel):
    emoji: str


class PropertyValue(BaseModel):
    value: Any


class MetaValue(BaseModel):
    value: Any = None


class TableGroupsPayload(IssueQuery):
    group_by: str = "status"


class TableRowsPayload(IssueQuery):
    group_by: str | None = None
    group_key: str | None = None


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
    actor_type, actor_id = _actor(user)
    try:
        issue = await svc.create_issue(
            db,
            payload.workspace_id,
            actor_type,
            actor_id,
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
    # compat single-value
    status: str | None = None,
    assignee_type: str | None = None,
    assignee_id: str | None = None,
    label_id: str | None = None,
    parent_issue_id: str | None = None,
    project_id: str | None = None,
    q: str | None = None,
    # filtros multi-valor (repetir o query param)
    statuses: list[str] = Query(default=[]),
    priorities: list[str] = Query(default=[]),
    assignee_ids: list[str] = Query(default=[]),
    label_ids: list[str] = Query(default=[]),
    project_ids: list[str] = Query(default=[]),
    ids: list[str] = Query(default=[]),
    include_no_project: bool = False,
    creator_id: str | None = None,
    creator_type: str | None = None,
    involves_user_id: str | None = None,
    metadata: str | None = None,  # JSON object {"key": value}
    properties: str | None = None,  # JSON object {"propertyId": value}
    top_level_only: bool = False,
    open_only: bool = False,
    scheduled: bool = False,
    sort: str | None = None,
    direction: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    import json as _json

    def _parse_json_obj(raw: str | None, name: str) -> dict | None:
        if not raw:
            return None
        try:
            obj = _json.loads(raw)
        except ValueError:
            raise HTTPException(400, f"{name} deve ser um objeto JSON válido")
        if not isinstance(obj, dict):
            raise HTTPException(400, f"{name} deve ser um objeto JSON")
        return obj

    filters = {
        "statuses": statuses or ([status] if status else None),
        "priorities": priorities or None,
        "assignee_type": assignee_type,
        "assignee_ids": assignee_ids or ([assignee_id] if assignee_id else None),
        "label_ids": label_ids or ([label_id] if label_id else None),
        "project_ids": project_ids or ([project_id] if project_id else None),
        "include_no_project": include_no_project,
        "ids": ids or None,
        "creator_id": creator_id,
        "creator_type": creator_type,
        "involves_user_id": involves_user_id,
        "parent_issue_id": parent_issue_id,
        "metadata": _parse_json_obj(metadata, "metadata"),
        "properties": _parse_json_obj(properties, "properties"),
        "top_level_only": top_level_only,
        "open_only": open_only,
        "scheduled": scheduled,
        "q": q,
    }
    try:
        items, total = await svc.query_issues(
            db, workspace_id, sort=sort, direction=direction, limit=limit, offset=offset, **filters
        )
    except svc.IssueError as e:
        raise _err(e)
    if limit is None and sort is None and total == len(items):
        return [svc.issue_to_dict(i) for i in items]  # compat com clientes antigos
    return {
        "items": [svc.issue_to_dict(i) for i in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/query")
async def query_issues(
    payload: IssueQuery, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    """Versão POST da listagem — p/ conjuntos grandes de ids/filtros."""
    try:
        items, total = await svc.query_issues(
            db,
            payload.workspace_id,
            sort=payload.sort,
            direction=payload.direction,
            limit=payload.limit,
            offset=payload.offset,
            **payload.filters(),
        )
    except svc.IssueError as e:
        raise _err(e)
    return {
        "items": [svc.issue_to_dict(i) for i in items],
        "total": total,
        "limit": payload.limit,
        "offset": payload.offset,
    }


@router.get("/search")
async def search_issues(
    workspace_id: str,
    q: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """Busca em título + descrição + comentários, com trecho do match."""
    return {"results": await svc.search_issues(db, workspace_id, q, limit)}


@router.get("/grouped")
async def grouped_issues(
    workspace_id: str,
    group_by: str = "status",
    per_group_limit: int = 50,
    statuses: list[str] = Query(default=[]),
    priorities: list[str] = Query(default=[]),
    assignee_ids: list[str] = Query(default=[]),
    label_ids: list[str] = Query(default=[]),
    project_ids: list[str] = Query(default=[]),
    open_only: bool = False,
    top_level_only: bool = False,
    q: str | None = None,
    sort: str | None = None,
    direction: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    filters = {
        "statuses": statuses or None,
        "priorities": priorities or None,
        "assignee_ids": assignee_ids or None,
        "label_ids": label_ids or None,
        "project_ids": project_ids or None,
        "open_only": open_only,
        "top_level_only": top_level_only,
        "q": q,
    }
    try:
        groups = await svc.grouped_issues(
            db, workspace_id, group_by,
            per_group_limit=per_group_limit, sort=sort, direction=direction, **filters,
        )
    except svc.IssueError as e:
        raise _err(e)
    return {"group_by": group_by, "groups": groups}


@router.post("/table/groups")
async def table_groups(
    payload: TableGroupsPayload, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        groups = await svc.table_groups(db, payload.workspace_id, payload.group_by, **payload.filters())
    except svc.IssueError as e:
        raise _err(e)
    return {"group_by": payload.group_by, "groups": groups}


@router.post("/table/rows")
async def table_rows(
    payload: TableRowsPayload, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        items, total = await svc.table_rows(
            db,
            payload.workspace_id,
            payload.group_by,
            payload.group_key,
            sort=payload.sort,
            direction=payload.direction,
            limit=payload.limit or 50,
            offset=payload.offset,
            **payload.filters(),
        )
    except svc.IssueError as e:
        raise _err(e)
    return {"items": [svc.issue_to_dict(i) for i in items], "total": total}


@router.post("/table/facets")
async def table_facets(
    payload: IssueQuery, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        facets = await svc.table_facets(db, payload.workspace_id, **payload.filters())
    except svc.IssueError as e:
        raise _err(e)
    return {"facets": facets}


@router.post("/batch-update")
async def batch_update(
    payload: BatchUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    at, aid = _actor(user)
    changes: dict[str, Any] = {}
    for field in (
        "status", "priority", "assignee_type", "assignee_id",
        "project_id", "due_date", "add_label_ids", "remove_label_ids",
    ):
        if field in payload.model_fields_set:
            changes[field] = getattr(payload, field)
    try:
        issues = await svc.batch_update_issues(
            db, payload.workspace_id, at, aid, payload.issue_ids, changes
        )
    except svc.IssueError as e:
        raise _err(e)
    return {"updated": len(issues), "items": [svc.issue_to_dict(i) for i in issues]}


@router.post("/batch-delete")
async def batch_delete(
    payload: BatchDelete, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    at, aid = _actor(user)
    try:
        n = await svc.batch_delete_issues(db, payload.workspace_id, at, aid, payload.issue_ids)
    except svc.IssueError as e:
        raise _err(e)
    return {"deleted": n}


@router.get("/by-key/{key}")
async def get_issue_by_key(
    key: str,
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """Resolve RYU-123 → issue (usado pelo CLI p/ aceitar keys em vez de UUIDs)."""
    row = await db.execute(
        select(Issue).where(Issue.workspace_id == workspace_id, Issue.key == key.upper())
    )
    issue = row.scalar_one_or_none()
    if issue is None:
        raise HTTPException(404, f"issue {key} não encontrada")
    return svc.issue_to_dict(issue, await svc.issue_labels(db, issue.id))


@router.get("/{issue_id}/usage")
async def issue_usage(issue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    """Usage agregado da issue (soma de todos os task runs — multica GetIssueUsage)."""
    try:
        issue = await svc.get_issue(db, issue_id)
    except svc.IssueError as e:
        raise _err(e)
    from ryu.models import AgentTask, TaskUsage

    task_ids = [
        tid for (tid,) in (await db.execute(select(AgentTask.id).where(AgentTask.issue_id == issue.id)))
    ]
    agg = {
        "issue_id": issue.id,
        "task_count": len(task_ids),
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "cost_usd": 0.0,
    }
    if task_ids:
        rows = await db.execute(select(TaskUsage).where(TaskUsage.task_id.in_(task_ids)))
        for u in rows.scalars():
            agg["input_tokens"] += u.input_tokens or 0
            agg["output_tokens"] += u.output_tokens or 0
            agg["cache_read_tokens"] += u.cache_read_tokens or 0
            agg["cache_write_tokens"] += u.cache_write_tokens or 0
            agg["cost_usd"] += u.cost_usd or 0.0
    return agg


@router.get("/{issue_id}")
async def get_issue(issue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        issue = await svc.get_issue(db, issue_id)
    except svc.IssueError as e:
        raise _err(e)
    d = svc.issue_to_dict(issue, await svc.issue_labels(db, issue.id))
    subs = await svc.list_issues(db, issue.workspace_id, parent_issue_id=issue.id)
    d["sub_issues"] = [svc.issue_to_dict(s) for s in subs]
    d["reactions"] = await svc.issue_reactions(db, issue.id)
    return d


@router.patch("/{issue_id}")
async def update_issue(
    issue_id: str,
    payload: IssueUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    changes = {k: getattr(payload, k) for k in payload.model_fields_set}
    actor_type, actor_id = _actor(user)
    try:
        issue = await svc.update_issue(db, issue_id, actor_type, actor_id, changes)
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


# ── Metadata (rotas de paridade multica) ──────────────────────────────
@router.get("/{issue_id}/metadata")
async def get_metadata(issue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        issue = await svc.get_issue(db, issue_id)
    except svc.IssueError as e:
        raise _err(e)
    return {"metadata": issue.meta or {}}


@router.put("/{issue_id}/metadata/{key}")
async def put_metadata_key(
    issue_id: str,
    key: str,
    payload: MetaValue,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    at, aid = _actor(user)
    if payload.value is None:
        raise HTTPException(400, "value é obrigatório; para remover use DELETE")
    try:
        meta = await svc.set_issue_meta(db, issue_id, at, aid, key, payload.value)
    except svc.IssueError as e:
        raise _err(e)
    return {"metadata": meta}


@router.delete("/{issue_id}/metadata/{key}")
async def delete_metadata_key(
    issue_id: str, key: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    at, aid = _actor(user)
    try:
        meta = await svc.delete_issue_meta(db, issue_id, at, aid, key)
    except svc.IssueError as e:
        raise _err(e)
    return {"metadata": meta}


# ── Propriedades customizadas (valores por issue) ─────────────────────
@router.put("/{issue_id}/properties/{property_id}")
async def set_issue_property(
    issue_id: str,
    property_id: str,
    payload: PropertyValue,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    from ryu.services import properties as props_svc

    at, aid = _actor(user)
    try:
        bag = await props_svc.set_issue_property(db, issue_id, property_id, at, aid, payload.value)
    except svc.IssueError as e:
        raise _err(e)
    return {"properties": bag}


@router.delete("/{issue_id}/properties/{property_id}")
async def delete_issue_property(
    issue_id: str, property_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    from ryu.services import properties as props_svc

    at, aid = _actor(user)
    try:
        bag = await props_svc.delete_issue_property(db, issue_id, property_id, at, aid)
    except svc.IssueError as e:
        raise _err(e)
    return {"properties": bag}


# ── Subscribers ───────────────────────────────────────────────────────
@router.get("/{issue_id}/subscribers")
async def list_subscribers(issue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        await svc.get_issue(db, issue_id)
    except svc.IssueError as e:
        raise _err(e)
    return [svc.subscriber_to_dict(s) for s in await svc.list_subscribers(db, issue_id)]


@router.post("/{issue_id}/subscribe", status_code=201)
async def subscribe_issue(
    issue_id: str,
    payload: SubscribePayload | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        await svc.get_issue(db, issue_id)
    except svc.IssueError as e:
        raise _err(e)
    at, aid = _actor(user)
    utype = (payload.user_type if payload and payload.user_type else at)
    uid_ = (payload.user_id if payload and payload.user_id else aid)
    if utype not in ("member", "agent"):
        raise HTTPException(400, f"user_type inválido: {utype}")
    sub = await svc.subscribe(db, issue_id, utype, uid_, "manual")
    await db.commit()
    return svc.subscriber_to_dict(sub) if sub else {"ok": True}


@router.post("/{issue_id}/unsubscribe", status_code=204)
async def unsubscribe_issue(
    issue_id: str,
    payload: SubscribePayload | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    at, aid = _actor(user)
    utype = (payload.user_type if payload and payload.user_type else at)
    uid_ = (payload.user_id if payload and payload.user_id else aid)
    await svc.unsubscribe(db, issue_id, utype, uid_)
    return Response(status_code=204)


# ── Reactions ─────────────────────────────────────────────────────────
@router.post("/{issue_id}/reactions")
async def add_issue_reaction(
    issue_id: str,
    payload: ReactionPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    at, aid = _actor(user)
    try:
        reactions = await svc.add_issue_reaction(db, issue_id, at, aid, payload.emoji)
    except svc.IssueError as e:
        raise _err(e)
    return {"reactions": reactions}


@router.delete("/{issue_id}/reactions")
async def remove_issue_reaction(
    issue_id: str,
    emoji: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    at, aid = _actor(user)
    try:
        reactions = await svc.remove_issue_reaction(db, issue_id, at, aid, emoji)
    except svc.IssueError as e:
        raise _err(e)
    return {"reactions": reactions}


@router.post("/comments/{comment_id}/reactions")
async def add_comment_reaction(
    comment_id: str,
    payload: ReactionPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    at, aid = _actor(user)
    try:
        reactions = await svc.add_comment_reaction(db, comment_id, at, aid, payload.emoji)
    except svc.IssueError as e:
        raise _err(e)
    return {"reactions": reactions}


@router.delete("/comments/{comment_id}/reactions")
async def remove_comment_reaction(
    comment_id: str,
    emoji: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    at, aid = _actor(user)
    try:
        reactions = await svc.remove_comment_reaction(db, comment_id, at, aid, emoji)
    except svc.IssueError as e:
        raise _err(e)
    return {"reactions": reactions}


# ── Resolve/unresolve de thread ───────────────────────────────────────
@router.post("/comments/{comment_id}/resolve")
async def resolve_comment(comment_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    at, aid = _actor(user)
    try:
        comment = await svc.resolve_comment(db, comment_id, at, aid, True)
    except svc.IssueError as e:
        raise _err(e)
    return svc.comment_to_dict(comment)


@router.delete("/comments/{comment_id}/resolve")
async def unresolve_comment(comment_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    at, aid = _actor(user)
    try:
        comment = await svc.resolve_comment(db, comment_id, at, aid, False)
    except svc.IssueError as e:
        raise _err(e)
    return svc.comment_to_dict(comment)


# ── Attachments da issue ──────────────────────────────────────────────
@router.get("/{issue_id}/attachments")
async def issue_attachments(issue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    from ryu.services import attachments as att_svc

    try:
        await svc.get_issue(db, issue_id)
    except svc.IssueError as e:
        raise _err(e)
    atts = await att_svc.list_issue_attachments(db, issue_id)
    return [att_svc.attachment_to_dict(a) for a in atts]


# ── Sub-issues ────────────────────────────────────────────────────────
@router.get("/{issue_id}/sub-issues")
async def sub_issues(issue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        issue = await svc.get_issue(db, issue_id)
    except svc.IssueError as e:
        raise _err(e)
    subs = await svc.list_issues(db, issue.workspace_id, parent_issue_id=issue.id)
    return [svc.issue_to_dict(s) for s in subs]


# ── Squad leader evaluation (multica router.go:1173) ──────────────────
class SquadEvaluatedIn(BaseModel):
    outcome: str  # action|no_action|failed
    squad_id: str | None = None


@router.post("/{issue_id}/squad-evaluated", status_code=201)
async def squad_evaluated(
    issue_id: str,
    payload: SquadEvaluatedIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """Registra a decisão do líder da squad (autenticável pelo token rat_)."""
    from ryu.services import squads as squads_svc
    from ryu.services.automation import AutomationError

    actor_type, actor_id = _actor(user)
    try:
        return await squads_svc.record_squad_evaluation(
            db, issue_id, actor_type, actor_id,
            outcome=payload.outcome, squad_id=payload.squad_id,
        )
    except AutomationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ── Comentários ───────────────────────────────────────────────────────
@router.post("/{issue_id}/comments", status_code=201)
async def create_comment(
    issue_id: str,
    payload: CommentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    actor_type, actor_id = _actor(user)
    try:
        comment = await svc.create_comment(db, issue_id, actor_type, actor_id, payload.body, payload.parent_comment_id)
    except svc.IssueError as e:
        raise _err(e)
    return svc.comment_to_dict(comment)


@router.get("/{issue_id}/comments")
async def list_comments(
    issue_id: str,
    response: Response,
    thread: str | None = None,
    tail: int | None = None,
    recent: int | None = None,
    before: datetime | None = None,
    before_id: str | None = None,
    since: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """Leitura de comentários com modos thread-aware (paridade multica):

    - sem params: timeline plana cronológica (cap 2000);
    - ?thread=<comment_id> [&tail=N] [&before=&before_id=]: raiz + réplicas;
    - ?recent=N [&before=&before_id=]: N threads mais ativas;
    - ?since=<ts>: polling incremental (réplicas > ts; raiz isenta).

    Cursor de próxima página nos headers X-Ryu-Next-Before /
    X-Ryu-Next-Before-Id — emitidos SÓ quando existe página mais antiga.
    """
    try:
        page = await svc.list_comments_paged(
            db, issue_id, thread=thread, tail=tail, recent=recent,
            before=before, before_id=before_id, since=since,
        )
    except svc.IssueError as e:
        raise _err(e)
    comments = page["comments"]
    reactions = await svc.comment_reactions_map(db, [c.id for c in comments])
    if page["next_before"] is not None:
        response.headers["X-Ryu-Next-Before"] = page["next_before"].isoformat()
        response.headers["X-Ryu-Next-Before-Id"] = page["next_before_id"] or ""
    return [svc.comment_to_dict(c, reactions.get(c.id, [])) for c in comments]


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
    from ryu.services import attachments as att_svc

    labels = await svc.issue_labels(db, issue.id)
    comments = await svc.list_comments(db, issue.id)
    subs = await svc.list_issues(db, ws.id, parent_issue_id=issue.id)
    activity = await svc.list_activity(db, issue.id, limit=50)
    attachments = [att_svc.attachment_to_dict(a) for a in await att_svc.list_issue_attachments(db, issue.id)]
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
            "attachments": attachments,
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


@pages_router.post("/w/{slug}/issues/{key}/attachments", response_class=HTMLResponse)
async def issue_page_upload(
    slug: str,
    key: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    from fastapi import UploadFile

    from ryu.services import attachments as att_svc

    ws = await _workspace_by_slug(db, slug)
    row = await db.execute(select(Issue).where(Issue.workspace_id == ws.id, Issue.key == key))
    issue = row.scalar_one_or_none()
    if issue is None:
        raise HTTPException(404, "issue não encontrada")
    form = await request.form()
    upload = form.get("file")
    if upload is None or not isinstance(upload, UploadFile):
        raise HTTPException(400, "arquivo é obrigatório")
    content = await upload.read()
    try:
        await att_svc.create_attachment(
            db, ws.id, "member", user.id,
            filename=upload.filename or "file", content=content,
            content_type=upload.content_type, issue_id=issue.id,
        )
    except att_svc.AttachmentError as e:
        raise HTTPException(e.status_code, e.message)
    attachments = [att_svc.attachment_to_dict(a) for a in await att_svc.list_issue_attachments(db, issue.id)]
    return templates.TemplateResponse(
        "issues/_attachments.html",
        {"request": request, "workspace": ws, "issue": issue, "attachments": attachments},
    )


@pages_router.post("/w/{slug}/issues/{key}/comments/{comment_id}/toggle-resolve", response_class=HTMLResponse)
async def issue_page_toggle_resolve(
    slug: str,
    key: str,
    comment_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    row = await db.execute(select(Issue).where(Issue.workspace_id == ws.id, Issue.key == key))
    issue = row.scalar_one_or_none()
    if issue is None:
        raise HTTPException(404, "issue não encontrada")
    from ryu.models import Comment as CommentModel

    comment = await db.get(CommentModel, comment_id)
    if comment is None or comment.issue_id != issue.id:
        raise HTTPException(404, "comentário não encontrado")
    try:
        await svc.resolve_comment(db, comment_id, "member", user.id, comment.resolved_at is None)
    except svc.IssueError as e:
        raise _err(e)
    comments = await svc.list_comments(db, issue.id)
    return templates.TemplateResponse(
        "issues/_comments.html",
        {"request": request, "user": user, "workspace": ws, "issue": issue, "comments": comments},
    )
