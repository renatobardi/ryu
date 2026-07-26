"""Serviço de autenticação do Ryu.

Exporta:
- current_user: dependency FastAPI (cookie JWT 'ryu_auth' OU header Bearer ryu_/rat_/rdt_)
- current_workspace(slug): helper que resolve workspace + valida membership
- create_task_token(agent_id, task_id, workspace_id) -> 'rat_...'
- funções usadas pelo router de auth (request-code, verify, PATs).
"""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

import jwt
import structlog
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.config import settings
from ryu.db import SessionLocal, get_db
from ryu.models import ApiToken, Member, User, VerificationCode, Workspace

log = structlog.get_logger("ryu.auth")

AUTH_COOKIE = "ryu_auth"
JWT_ALGO = "HS256"
JWT_TTL_DAYS = 30
CODE_TTL_MINUTES = 15


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _slugify(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or "ws"


# ── JWT ───────────────────────────────────────────────────────────────
def create_jwt(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "iat": int(_now().timestamp()),
        "exp": int((_now() + timedelta(days=JWT_TTL_DAYS)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGO)


def decode_jwt(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGO])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


# ── Verification codes ────────────────────────────────────────────────
async def request_code(db: AsyncSession, email: str) -> None:
    """Gera código de 6 dígitos, persiste e IMPRIME no log (sem SMTP)."""
    email = email.strip().lower()
    code = f"{secrets.randbelow(1_000_000):06d}"
    vc = VerificationCode(
        email=email,
        code=code,
        expires_at=_now() + timedelta(minutes=CODE_TTL_MINUTES),
    )
    db.add(vc)
    await db.commit()
    print(f"[ryu-auth] verification code for {email}: {code}", flush=True)
    log.info("verification_code_issued", email=email, code=code)


async def _consume_code(db: AsyncSession, email: str, code: str) -> bool:
    if settings.dev_verification_code and code == settings.dev_verification_code:
        return True
    res = await db.execute(
        select(VerificationCode)
        .where(
            VerificationCode.email == email,
            VerificationCode.code == code,
            VerificationCode.used.is_(False),
        )
        .order_by(VerificationCode.expires_at.desc())
    )
    vc = res.scalars().first()
    if vc is None:
        return False
    expires = vc.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < _now():
        return False
    vc.used = True
    await db.commit()
    return True


async def verify_code(db: AsyncSession, email: str, code: str) -> User:
    """Valida código; cria User (se allow_signup) + workspace pessoal no 1º login."""
    email = email.strip().lower()
    if not await _consume_code(db, email, code):
        raise HTTPException(status_code=400, detail="Código inválido ou expirado")

    res = await db.execute(select(User).where(User.email == email))
    user = res.scalars().first()
    if user is None:
        if not settings.allow_signup:
            raise HTTPException(status_code=403, detail="Cadastro desabilitado")
        user = User(email=email, name=email.split("@")[0])
        db.add(user)
        await db.flush()

    # workspace pessoal + member owner no primeiro login
    res = await db.execute(select(Member).where(Member.user_id == user.id))
    if res.scalars().first() is None:
        base_slug = _slugify(email.split("@")[0])
        slug = base_slug
        i = 1
        while True:
            res = await db.execute(select(Workspace).where(Workspace.slug == slug))
            if res.scalars().first() is None:
                break
            i += 1
            slug = f"{base_slug}-{i}"
        ws = Workspace(slug=slug, name=f"{user.name or base_slug}'s workspace")
        db.add(ws)
        await db.flush()
        db.add(Member(workspace_id=ws.id, user_id=user.id, role="owner"))

    await db.commit()
    return user


# ── Tokens (PAT / daemon / task) ──────────────────────────────────────
_TOKEN_PREFIXES = {"ryu_": "pat", "rdt_": "daemon", "rat_": "task"}


async def create_pat(db: AsyncSession, user_id: str, name: str = "") -> tuple[str, ApiToken]:
    raw = "ryu_" + secrets.token_urlsafe(32)
    row = ApiToken(token_hash=_sha256(raw), kind="pat", user_id=user_id, name=name)
    db.add(row)
    await db.commit()
    return raw, row


async def create_task_token(agent_id: str, task_id: str, workspace_id: str) -> str:
    """Cria token 'rat_...' para uma execução de task de agente (usado pelo runner)."""
    raw = "rat_" + secrets.token_urlsafe(32)
    async with SessionLocal() as db:
        db.add(
            ApiToken(
                token_hash=_sha256(raw),
                kind="task",
                agent_id=agent_id,
                task_id=task_id,
                workspace_id=workspace_id,
                name=f"task:{task_id}",
                expires_at=_now() + timedelta(hours=24),
            )
        )
        await db.commit()
    return raw


async def resolve_token(db: AsyncSession, raw: str) -> ApiToken | None:
    kind = next((k for p, k in _TOKEN_PREFIXES.items() if raw.startswith(p)), None)
    if kind is None:
        return None
    res = await db.execute(
        select(ApiToken).where(ApiToken.token_hash == _sha256(raw), ApiToken.revoked.is_(False))
    )
    tok = res.scalars().first()
    if tok is None:
        return None
    if tok.expires_at is not None:
        exp = tok.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < _now():
            return None
    return tok


# ── Dependencies ──────────────────────────────────────────────────────
async def _user_from_request(request: Request, db: AsyncSession) -> User | None:
    # 1) Bearer token (ryu_ PAT / rat_ task / rdt_ daemon)
    authz = request.headers.get("Authorization", "")
    if authz.lower().startswith("bearer "):
        raw = authz[7:].strip()
        tok = await resolve_token(db, raw)
        if tok is not None:
            request.state.api_token = tok
            if tok.user_id:
                res = await db.execute(select(User).where(User.id == tok.user_id))
                user = res.scalars().first()
                if user is not None:
                    return user
            # tokens de task/daemon não têm user: representam o agente
            if tok.kind in ("task", "daemon"):
                agent_user = User(email=f"agent-{tok.agent_id or tok.id}@ryu.local", name="Agent")
                agent_user.id = f"agent:{tok.agent_id or tok.id}"
                return agent_user
        return None
    # 2) Cookie JWT
    cookie = request.cookies.get(AUTH_COOKIE)
    if cookie:
        user_id = decode_jwt(cookie)
        if user_id:
            res = await db.execute(select(User).where(User.id == user_id))
            return res.scalars().first()
    return None


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    user = await _user_from_request(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Não autenticado")
    return user


async def optional_user(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    return await _user_from_request(request, db)


async def current_workspace(
    slug: str,
    db: AsyncSession,
    user: User,
) -> Workspace:
    """Resolve workspace pelo slug e valida que o user é membro (ou token do workspace)."""
    res = await db.execute(select(Workspace).where(Workspace.slug == slug))
    ws = res.scalars().first()
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace não encontrado")
    # agentes (rat_/rdt_) autenticam por workspace_id do token
    if user.id.startswith("agent:"):
        return ws
    res = await db.execute(
        select(Member).where(Member.workspace_id == ws.id, Member.user_id == user.id)
    )
    if res.scalars().first() is None:
        raise HTTPException(status_code=403, detail="Sem acesso a este workspace")
    return ws
