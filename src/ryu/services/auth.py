"""Serviço de autenticação do Ryu.

Exporta:
- current_user: dependency FastAPI (cookie JWT 'ryu_auth' OU header Bearer ryu_/rat_/rdt_)
- current_workspace(slug): helper que resolve workspace + valida membership
- create_task_token(agent_id, task_id, workspace_id) -> 'rat_...'
- funções usadas pelo router de auth (request-code, verify, PATs).
"""
from __future__ import annotations

import hashlib
import hmac
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
CSRF_COOKIE = "ryu_csrf"
JWT_ALGO = "HS256"
JWT_TTL_DAYS = 30
CODE_TTL_MINUTES = 15
CODE_MAX_ATTEMPTS = 5
PAT_PREFIX_LEN = 12
PAT_RENEW_THRESHOLD_DAYS = 7
PAT_RENEW_EXTENSION_DAYS = 90


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _slugify(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or "ws"


# ── CSRF (paridade multica auth/cookie.go) ────────────────────────────
def generate_csrf_token(auth_token: str) -> str:
    """hex(nonce) + '.' + hex(HMAC-SHA256(nonce, key=auth_token))."""
    nonce = secrets.token_bytes(16)
    sig = hmac.new(auth_token.encode(), nonce, hashlib.sha256).hexdigest()
    return nonce.hex() + "." + sig


def validate_csrf_token(csrf_header: str, auth_cookie: str) -> bool:
    if not csrf_header or not auth_cookie:
        return False
    parts = csrf_header.split(".", 1)
    if len(parts) != 2:
        return False
    try:
        nonce = bytes.fromhex(parts[0])
    except ValueError:
        return False
    expected = hmac.new(auth_cookie.encode(), nonce, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts[1])


def set_auth_cookies(response, token: str) -> None:
    """Cookie httponly de auth + cookie legível de CSRF."""
    max_age = JWT_TTL_DAYS * 24 * 3600
    response.set_cookie(
        key=AUTH_COOKIE, value=token, httponly=True, samesite="lax", max_age=max_age, path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=generate_csrf_token(token),
        httponly=False,
        samesite="lax",
        max_age=max_age,
        path="/",
    )


def clear_auth_cookies(response) -> None:
    response.delete_cookie(AUTH_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


# ── Signup gate (paridade multica checkSignupAllowed) ─────────────────
def _csv_list(raw: str) -> list[str]:
    return [x.strip().lower() for x in (raw or "").split(",") if x.strip()]


def check_signup_allowed(email: str, is_new_user: bool) -> None:
    """Levanta 403 quando um usuário NOVO não pode se cadastrar.

    Precedência multica: allowlist de e-mail vence, depois domínio, depois
    allow_signup; allowlist configurada sem match bloqueia mesmo com
    allow_signup=true. Usuários existentes sempre podem logar.
    """
    if not is_new_user:
        return
    email = email.strip().lower()
    domain = email.split("@", 1)[1] if "@" in email else ""
    allowed_emails = _csv_list(settings.allowed_emails)
    allowed_domains = _csv_list(settings.allowed_email_domains)
    if allowed_emails and email in allowed_emails:
        return
    if allowed_domains and domain in allowed_domains:
        return
    if not settings.allow_signup:
        raise HTTPException(
            status_code=403, detail="user registration is disabled on this self-hosted instance"
        )
    if allowed_emails or allowed_domains:
        raise HTTPException(
            status_code=403, detail="email address or domain not allowed on this instance"
        )


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
    """Gera código de 6 dígitos, persiste e envia via EmailService.

    Gate de signup ANTES de enviar (multica SendCode chama checkSignupAllowed)
    e cooldown de 60s por e-mail (429).
    """
    email = email.strip().lower()

    res = await db.execute(select(User).where(User.email == email))
    is_new_user = res.scalars().first() is None
    check_signup_allowed(email, is_new_user)

    # cooldown: máx. 1 código por auth_code_resend_seconds por e-mail
    cooldown = settings.auth_code_resend_seconds
    if cooldown > 0:
        res = await db.execute(
            select(VerificationCode)
            .where(VerificationCode.email == email)
            .order_by(VerificationCode.created_at.desc())
        )
        latest = res.scalars().first()
        if latest is not None and latest.created_at is not None:
            created = latest.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if (_now() - created).total_seconds() < cooldown:
                raise HTTPException(
                    status_code=429, detail="please wait before requesting another code"
                )

    code = f"{secrets.randbelow(1_000_000):06d}"
    vc = VerificationCode(
        email=email,
        code=code,
        expires_at=_now() + timedelta(minutes=CODE_TTL_MINUTES),
    )
    db.add(vc)
    await db.commit()
    from ryu.services.email import get_email_service

    try:
        await get_email_service().send_verification_code(email, code)
    except Exception as exc:  # noqa: BLE001
        log.error("verification_code_email_failed", email=email, error=str(exc))
        raise HTTPException(status_code=500, detail="failed to send verification code") from exc
    log.info("verification_code_issued", email=email)


async def _consume_code(db: AsyncSession, email: str, code: str) -> bool:
    code = code.strip()
    if settings.dev_verification_code and secrets.compare_digest(
        code, settings.dev_verification_code
    ):
        return True
    # só o código MAIS RECENTE não usado/não expirado com attempts < 5 vale
    res = await db.execute(
        select(VerificationCode)
        .where(VerificationCode.email == email, VerificationCode.used.is_(False))
        .order_by(VerificationCode.created_at.desc())
    )
    vc = res.scalars().first()
    if vc is None:
        return False
    expires = vc.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < _now() or (vc.attempts or 0) >= CODE_MAX_ATTEMPTS:
        return False
    if not secrets.compare_digest(code, vc.code):
        vc.attempts = (vc.attempts or 0) + 1
        await db.commit()
        return False
    vc.used = True
    await db.commit()
    return True


async def find_or_create_user(db: AsyncSession, email: str) -> tuple[User, bool]:
    """Retorna (user, is_new). Aplica o gate de signup (403) para usuário novo."""
    email = email.strip().lower()
    res = await db.execute(select(User).where(User.email == email))
    user = res.scalars().first()
    is_new = user is None
    check_signup_allowed(email, is_new)
    if user is None:
        user = User(email=email, name=email.split("@")[0])
        db.add(user)
        await db.flush()
    return user, is_new


async def ensure_personal_workspace(db: AsyncSession, user: User) -> None:
    """Workspace pessoal + member owner no primeiro login (pula slugs reservados)."""
    from ryu.services.workspaces import is_reserved_slug

    res = await db.execute(select(Member).where(Member.user_id == user.id))
    if res.scalars().first() is not None:
        return
    base_slug = _slugify(user.email.split("@")[0])
    slug = base_slug
    i = 1
    while True:
        if not is_reserved_slug(slug):
            res = await db.execute(select(Workspace).where(Workspace.slug == slug))
            if res.scalars().first() is None:
                break
        i += 1
        slug = f"{base_slug}-{i}"
    ws = Workspace(slug=slug, name=f"{user.name or base_slug}'s workspace")
    db.add(ws)
    await db.flush()
    db.add(Member(workspace_id=ws.id, user_id=user.id, role="owner"))


async def verify_code(db: AsyncSession, email: str, code: str) -> User:
    """Valida código; cria User (se permitido) + workspace pessoal no 1º login."""
    email = email.strip().lower()
    if not await _consume_code(db, email, code):
        raise HTTPException(status_code=400, detail="Código inválido ou expirado")

    user, _ = await find_or_create_user(db, email)
    await ensure_personal_workspace(db, user)
    await db.commit()
    return user


# ── Tokens (PAT / daemon / task) ──────────────────────────────────────
_TOKEN_PREFIXES = {"ryu_": "pat", "rdt_": "daemon", "rat_": "task"}


async def create_pat(
    db: AsyncSession, user_id: str, name: str = "", expires_in_days: int | None = None
) -> tuple[str, ApiToken]:
    raw = "ryu_" + secrets.token_urlsafe(32)
    expires_at = None
    if expires_in_days is not None and expires_in_days > 0:
        expires_at = _now() + timedelta(days=expires_in_days)
    row = ApiToken(
        token_hash=_sha256(raw),
        kind="pat",
        user_id=user_id,
        name=name,
        token_prefix=raw[:PAT_PREFIX_LEN],
        expires_at=expires_at,
    )
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
    # last_used_at (multica PAT metadata) — atualiza no máx. 1x/min p/ reduzir writes
    try:
        last = tok.last_used_at
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last is None or (_now() - last).total_seconds() > 60:
            tok.last_used_at = _now()
            await db.commit()
    except Exception:  # noqa: BLE001
        pass
    return tok


async def renew_current_pat(db: AsyncSession, raw: str) -> dict:
    """POST /api/auth/tokens/current/renew (multica RenewCurrentPersonalAccessToken).

    Estende expires_at em 90 dias APENAS quando restam <7 dias.
    renewed=false quando fora da janela ou quando expires_at é NULL.
    """
    if not raw.startswith("ryu_"):
        raise HTTPException(status_code=400, detail="only personal access tokens can be renewed")
    res = await db.execute(
        select(ApiToken).where(
            ApiToken.token_hash == _sha256(raw), ApiToken.kind == "pat",
            ApiToken.revoked.is_(False),
        )
    )
    tok = res.scalars().first()
    if tok is None:
        raise HTTPException(status_code=401, detail="token is no longer valid")
    if tok.expires_at is None:
        return {"expires_at": None, "renewed": False}
    exp = tok.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp - _now() > timedelta(days=PAT_RENEW_THRESHOLD_DAYS):
        return {"expires_at": exp.isoformat(), "renewed": False}
    tok.expires_at = _now() + timedelta(days=PAT_RENEW_EXTENSION_DAYS)
    await db.commit()
    return {"expires_at": tok.expires_at.isoformat(), "renewed": True}


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
