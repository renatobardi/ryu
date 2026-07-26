"""Rotas de autenticação: /api/auth/* (login por código, Google OAuth, PATs, config)."""
from __future__ import annotations

import re
import time
from collections import defaultdict, deque

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.config import settings
from ryu.db import get_db
from ryu.models import ApiToken, Member, User, Workspace
from ryu.services import auth as auth_service
from ryu.services.auth import current_user

log = structlog.get_logger("ryu.api.auth")

router = APIRouter()


# ── Rate limit (in-memory, nó único; multica RATE_LIMIT_AUTH*) ────────
_rl_hits: dict[str, deque[float]] = defaultdict(deque)
_RL_WINDOW = 60.0


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _rate_limit(request: Request, bucket: str, limit: int) -> None:
    if limit <= 0:
        return  # 0 = desabilitado
    key = f"{bucket}:{_client_ip(request)}"
    q = _rl_hits[key]
    now = time.monotonic()
    while q and now - q[0] > _RL_WINDOW:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(status_code=429, detail="too many requests")
    q.append(now)


async def rl_auth(request: Request) -> None:
    _rate_limit(request, "auth", settings.rate_limit_auth)


async def rl_auth_verify(request: Request) -> None:
    _rate_limit(request, "auth-verify", settings.rate_limit_auth_verify)


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


class GoogleLoginIn(BaseModel):
    code: str
    redirect_uri: str | None = None


class TokenCreateIn(BaseModel):
    name: str = ""
    expires_in_days: int | None = None


async def _user_workspaces(db: AsyncSession, user: User) -> list[dict]:
    res = await db.execute(
        select(Workspace, Member.role)
        .join(Member, Member.workspace_id == Workspace.id)
        .where(Member.user_id == user.id)
        .order_by(Workspace.created_at)
    )
    return [
        {"id": w.id, "slug": w.slug, "name": w.name, "role": role} for w, role in res.all()
    ]


def _login_payload(user: User, workspaces: list[dict]) -> dict:
    return {
        "ok": True,
        "user": {"id": user.id, "email": user.email, "name": user.name},
        "workspaces": workspaces,
    }


# ── Config pública (multica GET /api/config) ──────────────────────────
@router.get("/config")
async def auth_config():
    """Config pública p/ o frontend decidir o que renderizar (botão Google etc.)."""
    return {
        "allow_signup": settings.allow_signup,
        "google_client_id": settings.google_client_id or "",
        "workspace_creation_disabled": settings.disable_workspace_creation,
    }


# ── Login por código ──────────────────────────────────────────────────
@router.post("/request-code", dependencies=[Depends(rl_auth)])
async def request_code(body: RequestCodeIn, db: AsyncSession = Depends(get_db)):
    await auth_service.request_code(db, body.email)
    return {"ok": True, "message": "Código enviado"}


@router.post("/verify", dependencies=[Depends(rl_auth_verify)])
async def verify(body: VerifyIn, response: Response, db: AsyncSession = Depends(get_db)):
    user = await auth_service.verify_code(db, body.email, body.code)
    token = auth_service.create_jwt(user.id)
    auth_service.set_auth_cookies(response, token)
    return _login_payload(user, await _user_workspaces(db, user))


# ── Google OAuth (multica GoogleLogin) ────────────────────────────────
@router.post("/google", dependencies=[Depends(rl_auth)])
async def google_login(
    body: GoogleLoginIn, response: Response, db: AsyncSession = Depends(get_db)
):
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=503, detail="Google login is not configured")
    if not body.code:
        raise HTTPException(status_code=400, detail="code is required")

    redirect_uri = body.redirect_uri or settings.google_redirect_uri or ""

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": body.code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        except httpx.HTTPError as exc:
            log.error("google_token_exchange_failed", error=str(exc))
            raise HTTPException(status_code=502, detail="failed to exchange code with Google")
        if token_resp.status_code != 200:
            log.error(
                "google_token_exchange_error",
                status=token_resp.status_code,
                body=token_resp.text[:300],
            )
            raise HTTPException(status_code=400, detail="failed to exchange code with Google")
        access_token = token_resp.json().get("access_token", "")
        if not access_token:
            raise HTTPException(status_code=502, detail="failed to parse Google token response")
        try:
            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            info = userinfo_resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.error("google_userinfo_failed", error=str(exc))
            raise HTTPException(status_code=502, detail="failed to fetch user info from Google")

    email = (info.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Google account has no email")

    user, is_new = await auth_service.find_or_create_user(db, email)
    # nome/avatar do perfil Google quando o user acabou de ser criado
    if info.get("name") and user.name == email.split("@")[0]:
        user.name = info["name"]
    await auth_service.ensure_personal_workspace(db, user)
    await db.commit()

    token = auth_service.create_jwt(user.id)
    auth_service.set_auth_cookies(response, token)
    log.info("google_login_ok", user_id=user.id, email=email, is_new=is_new)
    payload = _login_payload(user, await _user_workspaces(db, user))
    payload["token"] = token
    return payload


@router.post("/logout")
async def logout(response: Response):
    auth_service.clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me")
async def me(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    workspaces: list[dict] = []
    if not user.id.startswith("agent:"):
        workspaces = await _user_workspaces(db, user)
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "workspaces": workspaces,
    }


# ── PATs ──────────────────────────────────────────────────────────────
def _pat_to_dict(t: ApiToken) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "token_prefix": t.token_prefix or "",
        "created_at": t.created_at,
        "expires_at": t.expires_at,
        "last_used_at": t.last_used_at,
    }


@router.post("/tokens")
async def create_token(
    body: TokenCreateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.id.startswith("agent:"):
        raise HTTPException(status_code=403, detail="Apenas usuários podem criar PATs")
    raw, row = await auth_service.create_pat(db, user.id, body.name, body.expires_in_days)
    return {**_pat_to_dict(row), "token": raw}  # token exibido apenas uma vez


@router.get("/tokens")
async def list_tokens(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(ApiToken)
        .where(ApiToken.user_id == user.id, ApiToken.kind == "pat", ApiToken.revoked.is_(False))
        .order_by(ApiToken.created_at.desc())
    )
    return [_pat_to_dict(t) for t in res.scalars().all()]


@router.post("/tokens/current/renew")
async def renew_current_token(request: Request, db: AsyncSession = Depends(get_db)):
    authz = request.headers.get("Authorization", "")
    if not authz.lower().startswith("bearer "):
        raise HTTPException(
            status_code=400, detail="only personal access tokens can be renewed"
        )
    return await auth_service.renew_current_pat(db, authz[7:].strip())


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
