"""API do catálogo de PROPRIEDADES CUSTOMIZADAS (montar com prefix /api/properties).

Os valores por issue (PUT/DELETE /api/issues/{id}/properties/{propertyId})
vivem no router de issues.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import get_db
from ryu.models import User
from ryu.services import properties as svc
from ryu.services.auth import current_user
from ryu.services.issues import IssueError

router = APIRouter()


def _err(e: IssueError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=e.message)


def _actor(user: User) -> tuple[str, str]:
    if user.id.startswith("agent:"):
        return "agent", user.id.split(":", 1)[1]
    return "member", user.id


class PropertyCreate(BaseModel):
    workspace_id: str
    name: str
    type: str
    description: str = ""
    config: dict | None = None
    icon: str = ""


class PropertyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config: dict | None = None
    icon: str | None = None
    position: float | None = None
    archived: bool | None = None
    type: str | None = None  # imutável — aceito só p/ retornar 400 claro


@router.get("")
async def list_properties(
    workspace_id: str,
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    props = await svc.list_properties(db, workspace_id, include_archived=include_archived)
    return [svc.property_to_dict(p) for p in props]


@router.post("", status_code=201)
async def create_property(
    payload: PropertyCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    at, aid = _actor(user)
    try:
        prop = await svc.create_property(
            db,
            payload.workspace_id,
            at,
            aid,
            name=payload.name,
            type=payload.type,
            description=payload.description,
            config=payload.config,
            icon=payload.icon,
        )
    except IssueError as e:
        raise _err(e)
    return svc.property_to_dict(prop)


@router.get("/{property_id}")
async def get_property(
    property_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        prop = await svc.get_property(db, property_id)
    except IssueError as e:
        raise _err(e)
    return svc.property_to_dict(prop)


@router.patch("/{property_id}")
async def update_property(
    property_id: str,
    payload: PropertyUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    at, aid = _actor(user)
    changes: dict[str, Any] = {k: getattr(payload, k) for k in payload.model_fields_set}
    try:
        prop = await svc.update_property(db, property_id, at, aid, changes)
    except IssueError as e:
        raise _err(e)
    return svc.property_to_dict(prop)
