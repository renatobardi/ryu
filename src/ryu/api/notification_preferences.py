"""API de preferências de notificação por (workspace, usuário) — multica 064.

Montar em main.py com prefix="/api/notification-preferences".
Rotas: GET (retorna {} sem registro), PATCH (merge), PUT (substitui).
Grupos válidos: assignments|status_changes|comments|updates|agent_activity|
system_notifications; valores: all|muted.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import get_db
from ryu.models import NotificationPreference, User
from ryu.services.auth import current_user
from ryu.services.workspaces import require_member

router = APIRouter()

VALID_GROUPS = {
    "assignments",
    "status_changes",
    "comments",
    "updates",
    "agent_activity",
    "system_notifications",
}
VALID_VALUES = {"all", "muted"}


class PreferencesIn(BaseModel):
    preferences: dict[str, str]


def _validate(prefs: dict[str, str]) -> None:
    for k, v in prefs.items():
        if k not in VALID_GROUPS:
            raise HTTPException(status_code=400, detail=f"invalid preference group: {k}")
        if v not in VALID_VALUES:
            raise HTTPException(status_code=400, detail=f"invalid preference value: {v}")


async def _load(db: AsyncSession, workspace_id: str, user_id: str) -> NotificationPreference | None:
    res = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.workspace_id == workspace_id,
            NotificationPreference.user_id == user_id,
        )
    )
    return res.scalars().first()


def _response(workspace_id: str, prefs: dict) -> dict:
    return {"workspace_id": workspace_id, "preferences": prefs or {}}


@router.get("")
async def get_preferences(
    workspace_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_member(db, workspace_id, user)
    row = await _load(db, workspace_id, user.id)
    return _response(workspace_id, row.preferences if row else {})


@router.patch("")
async def patch_preferences(
    workspace_id: str,
    body: PreferencesIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_member(db, workspace_id, user)
    _validate(body.preferences)
    row = await _load(db, workspace_id, user.id)
    if row is None:
        row = NotificationPreference(
            workspace_id=workspace_id, user_id=user.id, preferences=dict(body.preferences)
        )
        db.add(row)
    else:
        merged = dict(row.preferences or {})
        merged.update(body.preferences)
        row.preferences = merged
    await db.commit()
    return _response(workspace_id, row.preferences)


@router.put("")
async def put_preferences(
    workspace_id: str,
    body: PreferencesIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_member(db, workspace_id, user)
    _validate(body.preferences)
    row = await _load(db, workspace_id, user.id)
    if row is None:
        row = NotificationPreference(
            workspace_id=workspace_id, user_id=user.id, preferences=dict(body.preferences)
        )
        db.add(row)
    else:
        row.preferences = dict(body.preferences)
    await db.commit()
    return _response(workspace_id, row.preferences)
