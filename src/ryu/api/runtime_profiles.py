"""API de RUNTIME PROFILES por workspace (multica 120_runtime_profile).

`router`: montar com prefix="/api/runtime-profiles" no main.py.

- POST   ""            cria (admin/owner do workspace)
- GET    ""            lista por workspace (membros; private só do criador)
- GET    /{id}         detalhe
- PATCH  /{id}         atualiza (admin/owner ou criador)
- DELETE /{id}         remove (admin/owner ou criador; falha se agente usa)

O runner resolve o profile no build do comando (adapters.build_command):
command_name substitui o binário, fixed_args entram antes dos extra_args.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import get_db
from ryu.models import Agent, Member, RuntimeProfile, User
from ryu.runner.adapters import PROTOCOL_FAMILIES
from ryu.services.auth import current_user

router = APIRouter()

VISIBILITIES = ["workspace", "private"]


def profile_to_dict(p: RuntimeProfile) -> dict:
    return {
        "id": p.id,
        "workspace_id": p.workspace_id,
        "display_name": p.display_name,
        "protocol_family": p.protocol_family,
        "command_name": p.command_name,
        "fixed_args": list(p.fixed_args or []),
        "visibility": p.visibility,
        "created_by": p.created_by,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


class ProfileCreate(BaseModel):
    workspace_id: str
    display_name: str
    protocol_family: str = "claude"
    command_name: str
    fixed_args: list[str] = []
    visibility: str = "workspace"


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    protocol_family: str | None = None
    command_name: str | None = None
    fixed_args: list[str] | None = None
    visibility: str | None = None


async def _member_role(db: AsyncSession, user: User, workspace_id: str) -> str | None:
    if user.id.startswith("agent:"):
        return None
    res = await db.execute(
        select(Member).where(Member.workspace_id == workspace_id, Member.user_id == user.id)
    )
    m = res.scalars().first()
    return m.role if m else None


async def _require_member(db: AsyncSession, user: User, workspace_id: str) -> str:
    role = await _member_role(db, user, workspace_id)
    if role is None and not user.id.startswith("agent:"):
        raise HTTPException(403, "sem acesso a este workspace")
    return role or "agent"


async def _require_admin(db: AsyncSession, user: User, workspace_id: str) -> None:
    role = await _member_role(db, user, workspace_id)
    if role not in ("owner", "admin"):
        raise HTTPException(403, "apenas admin/owner do workspace pode gerenciar runtime profiles")


def _validate(protocol_family: str | None, visibility: str | None, command_name: str | None) -> None:
    if protocol_family is not None and protocol_family not in PROTOCOL_FAMILIES:
        raise HTTPException(422, f"protocol_family inválido: {protocol_family} (suportados: {', '.join(PROTOCOL_FAMILIES)})")
    if visibility is not None and visibility not in VISIBILITIES:
        raise HTTPException(422, f"visibility inválida: {visibility}")
    if command_name is not None and not command_name.strip():
        raise HTTPException(422, "command_name é obrigatório")


async def _get_profile(db: AsyncSession, profile_id: str) -> RuntimeProfile:
    p = await db.get(RuntimeProfile, profile_id)
    if p is None:
        raise HTTPException(404, "runtime profile não encontrado")
    return p


async def _can_mutate(db: AsyncSession, user: User, p: RuntimeProfile) -> bool:
    if p.created_by == user.id:
        return True
    role = await _member_role(db, user, p.workspace_id)
    return role in ("owner", "admin")


@router.post("", status_code=201)
async def create_profile(payload: ProfileCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await _require_admin(db, user, payload.workspace_id)
    _validate(payload.protocol_family, payload.visibility, payload.command_name)
    p = RuntimeProfile(
        workspace_id=payload.workspace_id,
        display_name=payload.display_name.strip() or payload.command_name,
        protocol_family=payload.protocol_family,
        command_name=payload.command_name.strip(),
        fixed_args=list(payload.fixed_args or []),
        visibility=payload.visibility,
        created_by=user.id,
    )
    db.add(p)
    await db.commit()
    return profile_to_dict(p)


@router.get("")
async def list_profiles(workspace_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await _require_member(db, user, workspace_id)
    res = await db.execute(
        select(RuntimeProfile).where(RuntimeProfile.workspace_id == workspace_id).order_by(RuntimeProfile.display_name)
    )
    profiles = [
        p for p in res.scalars()
        if p.visibility == "workspace" or p.created_by == user.id or user.id.startswith("agent:")
    ]
    return [profile_to_dict(p) for p in profiles]


@router.get("/{profile_id}")
async def get_profile(profile_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    p = await _get_profile(db, profile_id)
    await _require_member(db, user, p.workspace_id)
    if p.visibility == "private" and p.created_by != user.id and not await _can_mutate(db, user, p):
        raise HTTPException(403, "profile privado")
    return profile_to_dict(p)


@router.patch("/{profile_id}")
async def update_profile(profile_id: str, payload: ProfileUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    p = await _get_profile(db, profile_id)
    if not await _can_mutate(db, user, p):
        raise HTTPException(403, "sem permissão para alterar este profile")
    changes = {k: getattr(payload, k) for k in payload.model_fields_set}
    _validate(changes.get("protocol_family"), changes.get("visibility"), changes.get("command_name"))
    for k, v in changes.items():
        if v is not None:
            setattr(p, k, v.strip() if k in ("display_name", "command_name") and isinstance(v, str) else v)
    await db.commit()
    return profile_to_dict(p)


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(profile_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    p = await _get_profile(db, profile_id)
    if not await _can_mutate(db, user, p):
        raise HTTPException(403, "sem permissão para remover este profile")
    res = await db.execute(select(Agent.id).where(Agent.profile_id == profile_id).limit(1))
    if res.first() is not None:
        raise HTTPException(409, "profile em uso por agente(s) — desvincule antes de remover")
    await db.delete(p)
    await db.commit()
    return Response(status_code=204)
