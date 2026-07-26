"""Rotas de autenticação: /api/auth/* (login por código de e-mail, PATs)."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import get_db
from ryu.models import ApiToken, Member, User, Workspace
from ryu.services import auth as auth_service
from ryu.services.auth import AUTH_COOKIE, current_user

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RequestCodeIn(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("e-mail inválido")
        return v


class VerifyIn(BaseModel):
    email: str
    code: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("e-mail inválido")
        return v


class TokenCreateIn(BaseModel):
    name: str = ""


# ── Login por código ──────────────────────────────────────────────────
@router.post("/request-code")
async def request_code(body: RequestCodeIn, db: AsyncSession = Depends(get_db)):
    await auth_service.request_code(db, body.email)
    return {"ok": True, "message": "Código enviado (veja o log do servidor)"}


@router.post("/verify")
async def verify(body: VerifyIn, response: Response, db: AsyncSession = Depends(get_db)):
    user = await auth_service.verify_code(db, body.email, body.code)
    token = auth_service.create_jwt(user.id)
    response.set_cookie(
        key=AUTH_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=auth_service.JWT_TTL_DAYS * 24 * 3600,
        path="/",
    )
    res = await db.execute(
        select(Workspace)
        .join(Member, Member.workspace_id == Workspace.id)
        .where(Member.user_id == user.id)
        .order_by(Workspace.created_at)
    )
    workspaces = res.scalars().all()
    return {
        "ok": True,
        "user": {"id": user.id, "email": user.email, "name": user.name},
        "workspaces": [{"id": w.id, "slug": w.slug, "name": w.name} for w in workspaces],
    }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(AUTH_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    workspaces: list[dict] = []
    if not user.id.startswith("agent:"):
        res = await db.execute(
            select(Workspace, Member.role)
            .join(Member, Member.workspace_id == Workspace.id)
            .where(Member.user_id == user.id)
            .order_by(Workspace.created_at)
        )
        workspaces = [
            {"id": w.id, "slug": w.slug, "name": w.name, "role": role}
            for w, role in res.all()
        ]
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "workspaces": workspaces,
    }


# ── PATs ──────────────────────────────────────────────────────────────
@router.post("/tokens")
async def create_token(
    body: TokenCreateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.id.startswith("agent:"):
        raise HTTPException(status_code=403, detail="Apenas usuários podem criar PATs")
    raw, row = await auth_service.create_pat(db, user.id, body.name)
    return {
        "id": row.id,
        "name": row.name,
        "token": raw,  # exibido apenas uma vez
        "created_at": row.created_at,
    }


@router.get("/tokens")
async def list_tokens(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(ApiToken)
        .where(ApiToken.user_id == user.id, ApiToken.kind == "pat", ApiToken.revoked.is_(False))
        .order_by(ApiToken.created_at.desc())
    )
    return [
        {"id": t.id, "name": t.name, "created_at": t.created_at, "expires_at": t.expires_at}
        for t in res.scalars().all()
    ]


@router.delete("/tokens/{token_id}")
async def delete_token(
    token_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(ApiToken).where(
            ApiToken.id == token_id, ApiToken.user_id == user.id, ApiToken.kind == "pat"
        )
    )
    tok = res.scalars().first()
    if tok is None:
        raise HTTPException(status_code=404, detail="Token não encontrado")
    tok.revoked = True
    await db.commit()
    return {"ok": True}
