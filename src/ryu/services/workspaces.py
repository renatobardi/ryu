"""Serviço do domínio WORKSPACE-AUTH (ciclo 1).

- RESERVED_SLUGS + is_reserved_slug/validate_slug (multica reserved_slugs.json)
- get_member / require_role — enforcement owner/admin/member
- CRUD de workspace, gestão de membros e sistema de convites.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.config import settings
from ryu.models import Invitation, Member, User, Workspace

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Slugs reservados: rotas top-level do ryu + lista do multica (adaptada).
RESERVED_SLUGS = frozenset(
    {
        # rotas top-level do ryu
        "login", "logout", "w", "ws", "api", "static", "uploads", "healthz",
        "cli-login", "invite", "invitations", "docs", "redoc", "openapi.json",
        # auth flow
        "signin", "signout", "signup", "auth", "oauth", "callback", "verify",
        "reset", "password", "onboarding",
        # plataforma / marketing
        "admin", "ryu", "multica", "www", "new", "home", "homepage", "dashboard",
        "help", "about", "pricing", "changelog", "support", "status", "legal",
        "privacy", "terms", "security", "contact", "blog", "careers", "press",
        "download",
        # conta / billing
        "profile", "account", "billing", "notifications", "search", "members",
        # segmentos de rota de workspace
        "issues", "projects", "autopilots", "agents", "squads", "inbox",
        "my-issues", "usage", "runtimes", "skills", "settings", "workspaces",
        "teams", "board", "chat",
        # API / integrações
        "v1", "v2", "graphql", "webhooks", "sdk", "tokens", "cli",
        # ops / observabilidade
        "health", "readyz", "metrics", "ping",
        # RFC 2142 + confusáveis de hostname
        "postmaster", "abuse", "noreply", "webmaster", "hostmaster",
        "mail", "ftp", "cdn", "assets", "public", "files",
    }
)

VALID_ROLES = ("owner", "admin", "member")


def now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def is_reserved_slug(slug: str) -> bool:
    return slug in RESERVED_SLUGS


def validate_slug(slug: str) -> str:
    """Valida formato + reserva. Levanta HTTPException 400."""
    slug = slug.strip().lower()
    if not slug:
        raise HTTPException(status_code=400, detail="slug is required")
    if not SLUG_RE.match(slug):
        raise HTTPException(
            status_code=400,
            detail="slug must contain only lowercase letters, numbers, and hyphens",
        )
    if is_reserved_slug(slug):
        raise HTTPException(status_code=400, detail="slug is reserved")
    return slug


def generate_issue_prefix(name: str) -> str:
    letters = re.sub(r"[^a-zA-Z]", "", name)
    if not letters:
        return "WS"
    return letters.upper()[:3]


# ── Papéis ────────────────────────────────────────────────────────────
async def get_member(db: AsyncSession, workspace_id: str, user_id: str) -> Member | None:
    res = await db.execute(
        select(Member).where(Member.workspace_id == workspace_id, Member.user_id == user_id)
    )
    return res.scalars().first()


async def require_member(db: AsyncSession, workspace_id: str, user: User) -> Member:
    member = await get_member(db, workspace_id, user.id)
    if member is None:
        raise HTTPException(status_code=403, detail="Sem acesso a este workspace")
    return member


async def require_access(db: AsyncSession, workspace_id: str, user: User) -> str:
    """Papel do user no workspace, 403 se não tiver acesso.

    Agentes (tokens rat_/rdt_, user.id = 'agent:<id>') autenticam pelo próprio
    token e passam como papel 'agent' — mesmo critério de current_workspace.
    """
    if user.id.startswith("agent:"):
        return "agent"
    return (await require_member(db, workspace_id, user)).role


async def require_role(
    db: AsyncSession, workspace_id: str, user: User, roles: tuple[str, ...]
) -> Member:
    """Dependency-helper: valida membership E papel (multica RequireWorkspaceRoleFromURL)."""
    member = await require_member(db, workspace_id, user)
    if member.role not in roles:
        raise HTTPException(status_code=403, detail="insufficient permissions")
    return member


async def count_owners(db: AsyncSession, workspace_id: str) -> int:
    res = await db.execute(
        select(Member).where(Member.workspace_id == workspace_id, Member.role == "owner")
    )
    return len(list(res.scalars()))


# ── Serialização ──────────────────────────────────────────────────────
def workspace_to_dict(ws: Workspace) -> dict:
    return {
        "id": ws.id,
        "name": ws.name,
        "slug": ws.slug,
        "description": ws.description or "",
        "context": ws.context or "",
        "settings": ws.settings or {},
        "repos": ws.repos or [],
        "issue_prefix": ws.issue_prefix,
        "avatar_url": ws.avatar_url,
        "created_at": ws.created_at.isoformat() if ws.created_at else None,
        "updated_at": ws.updated_at.isoformat() if ws.updated_at else None,
    }


def member_to_dict(m: Member, user: User | None = None) -> dict:
    out = {
        "id": m.id,
        "workspace_id": m.workspace_id,
        "user_id": m.user_id,
        "role": m.role,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }
    if user is not None:
        out["name"] = user.name
        out["email"] = user.email
    return out


def invitation_to_dict(inv: Invitation, extra: dict | None = None) -> dict:
    out = {
        "id": inv.id,
        "workspace_id": inv.workspace_id,
        "inviter_id": inv.inviter_id,
        "invitee_email": inv.invitee_email,
        "invitee_user_id": inv.invitee_user_id,
        "role": inv.role,
        "status": inv.status,
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "updated_at": inv.updated_at.isoformat() if inv.updated_at else None,
    }
    if extra:
        out.update(extra)
    return out


# ── Convites ──────────────────────────────────────────────────────────
def invitation_expired(inv: Invitation) -> bool:
    exp = _aware(inv.expires_at)
    return exp is not None and exp < now()


async def expire_stale_invitations(
    db: AsyncSession, workspace_id: str | None = None, invitee_email: str | None = None
) -> int:
    """Marca pendentes vencidos como expired (multica ExpireStalePendingInvitations)."""
    stmt = select(Invitation).where(Invitation.status == "pending")
    if workspace_id:
        stmt = stmt.where(Invitation.workspace_id == workspace_id)
    if invitee_email:
        stmt = stmt.where(Invitation.invitee_email == invitee_email)
    n = 0
    for inv in (await db.execute(stmt)).scalars():
        if invitation_expired(inv):
            inv.status = "expired"
            n += 1
    if n:
        await db.flush()
    return n


def new_invitation(workspace_id: str, inviter_id: str, email: str, role: str,
                   invitee_user_id: str | None) -> Invitation:
    return Invitation(
        workspace_id=workspace_id,
        inviter_id=inviter_id,
        invitee_email=email,
        invitee_user_id=invitee_user_id,
        role=role,
        status="pending",
        expires_at=now() + timedelta(days=settings.invitation_ttl_days),
    )


# ── Delete de workspace (cascade manual — SQLite sem FK ON DELETE) ────
async def delete_workspace_cascade(db: AsyncSession, workspace_id: str) -> None:
    from ryu import models as m

    # tabelas com workspace_id direto
    ws_tables = [
        m.Member, m.Invitation, m.NotificationPreference, m.Project, m.Issue,
        m.Label, m.Attachment, m.IssueProperty, m.IssueReaction, m.CommentReaction,
        m.PinnedItem, m.ActivityLog, m.AgentRuntime, m.Agent, m.RuntimeProfile,
        m.AgentTask, m.TaskUsage, m.Skill, m.Squad, m.Autopilot,
        m.AutopilotRuleVersion, m.WebhookDelivery, m.ChatSession, m.ChatPinnedAgent,
        m.InboxItem,
    ]
    for model in ws_tables:
        await db.execute(delete(model).where(model.workspace_id == workspace_id))
    await db.execute(delete(m.Workspace).where(m.Workspace.id == workspace_id))
