"""API de workspaces, membros e convites (workspace-auth ciclo 1).

- `router`: montar em main.py com prefix="/api/workspaces".
- `invitations_router`: user-scoped, montar com prefix="/api/invitations".
- `pages_router`: página HTML /w/{slug}/members (+ /invite/{id}), SEM prefixo.

Paridade multica: server/internal/handler/workspace.go + invitation.go,
com RequireWorkspaceRoleFromURL via ryu.services.workspaces.require_role.
"""
from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.config import settings
from ryu.db import get_db
from ryu.models import Invitation, Member, User, Workspace
from ryu.realtime.hub import hub
from ryu.services import workspaces as svc
from ryu.services.auth import current_user, current_workspace

log = structlog.get_logger("ryu.api.workspaces")

router = APIRouter()
invitations_router = APIRouter()
pages_router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ── Schemas ───────────────────────────────────────────────────────────
class WorkspaceCreateIn(BaseModel):
    name: str
    slug: str
    description: str | None = None
    context: str | None = None
    issue_prefix: str | None = None


class WorkspaceUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    context: str | None = None
    settings: dict | None = None
    repos: list | None = None
    issue_prefix: str | None = None
    avatar_url: str | None = None


class MemberInviteIn(BaseModel):
    email: str
    role: str = "member"


class MemberUpdateIn(BaseModel):
    role: str


async def _load_workspace(db: AsyncSession, workspace_id: str) -> Workspace:
    """Resolve por id OU slug (o CLI usa slug em alguns fluxos)."""
    res = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = res.scalars().first()
    if ws is None:
        res = await db.execute(select(Workspace).where(Workspace.slug == workspace_id))
        ws = res.scalars().first()
    if ws is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return ws


# ── Workspace CRUD ────────────────────────────────────────────────────
@router.get("")
async def list_workspaces(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    res = await db.execute(
        select(Workspace, Member.role)
        .join(Member, Member.workspace_id == Workspace.id)
        .where(Member.user_id == user.id)
        .order_by(Workspace.created_at)
    )
    return [{**svc.workspace_to_dict(w), "role": role} for w, role in res.all()]


@router.post("", status_code=201)
async def create_workspace(
    body: WorkspaceCreateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if settings.disable_workspace_creation:
        raise HTTPException(
            status_code=403, detail="workspace creation is disabled for this instance"
        )
    if user.id.startswith("agent:"):
        raise HTTPException(status_code=403, detail="apenas usuários criam workspaces")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name and slug are required")
    slug = svc.validate_slug(body.slug)

    res = await db.execute(select(Workspace).where(Workspace.slug == slug))
    if res.scalars().first() is not None:
        raise HTTPException(status_code=409, detail="workspace slug already exists")

    prefix = (body.issue_prefix or "").strip().upper() or svc.generate_issue_prefix(name)
    ws = Workspace(
        name=name,
        slug=slug,
        issue_prefix=prefix,
        description=(body.description or ""),
        context=(body.context or ""),
    )
    db.add(ws)
    await db.flush()
    db.add(Member(workspace_id=ws.id, user_id=user.id, role="owner"))
    await db.commit()
    log.info("workspace_created", workspace_id=ws.id, slug=slug, user_id=user.id)
    return svc.workspace_to_dict(ws)


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ws = await _load_workspace(db, workspace_id)
    await svc.require_member(db, ws.id, user)
    return svc.workspace_to_dict(ws)


async def _update_workspace(
    workspace_id: str, body: WorkspaceUpdateIn, user: User, db: AsyncSession
) -> dict:
    ws = await _load_workspace(db, workspace_id)
    await svc.require_role(db, ws.id, user, ("owner", "admin"))
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        ws.name = name
    if body.description is not None:
        ws.description = body.description
    if body.context is not None:
        ws.context = body.context
    if body.settings is not None:
        ws.settings = body.settings
    if body.repos is not None:
        ws.repos = body.repos
    if body.issue_prefix is not None:
        prefix = body.issue_prefix.strip().upper()
        if prefix:
            ws.issue_prefix = prefix
    if body.avatar_url is not None:
        ws.avatar_url = body.avatar_url
    await db.commit()
    data = svc.workspace_to_dict(ws)
    await hub.publish(ws.id, "workspace:updated", {"workspace": data})
    return data


@router.patch("/{workspace_id}")
async def patch_workspace(
    workspace_id: str,
    body: WorkspaceUpdateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _update_workspace(workspace_id, body, user, db)


@router.put("/{workspace_id}")
async def put_workspace(
    workspace_id: str,
    body: WorkspaceUpdateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _update_workspace(workspace_id, body, user, db)


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ws = await _load_workspace(db, workspace_id)
    workspace_id = ws.id
    await svc.require_role(db, workspace_id, user, ("owner",))
    await svc.delete_workspace_cascade(db, workspace_id)
    await db.commit()
    log.info("workspace_deleted", workspace_id=workspace_id, user_id=user.id)
    await hub.publish(workspace_id, "workspace:deleted", {"workspace_id": workspace_id})
    return Response(status_code=204)


# ── Membros ───────────────────────────────────────────────────────────
@router.get("/{workspace_id}/members")
async def list_members(
    workspace_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace_id = (await _load_workspace(db, workspace_id)).id
    await svc.require_member(db, workspace_id, user)
    res = await db.execute(
        select(Member, User)
        .join(User, User.id == Member.user_id)
        .where(Member.workspace_id == workspace_id)
        .order_by(Member.created_at)
    )
    return [svc.member_to_dict(m, u) for m, u in res.all()]


@router.patch("/{workspace_id}/members/{member_id}")
async def update_member(
    workspace_id: str,
    member_id: str,
    body: MemberUpdateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    requester = await svc.require_role(db, workspace_id, user, ("owner", "admin"))
    res = await db.execute(select(Member).where(Member.id == member_id))
    target = res.scalars().first()
    if target is None or target.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="member not found")
    role = body.role.strip()
    if role not in svc.VALID_ROLES:
        raise HTTPException(status_code=400, detail="invalid member role")
    # admin não mexe em owner nem promove a owner (multica UpdateMember)
    if (target.role == "owner" or role == "owner") and requester.role != "owner":
        raise HTTPException(status_code=403, detail="insufficient permissions")
    if target.role == "owner" and role != "owner":
        if await svc.count_owners(db, workspace_id) <= 1:
            raise HTTPException(status_code=400, detail="workspace must have at least one owner")
    target.role = role
    await db.commit()
    res = await db.execute(select(User).where(User.id == target.user_id))
    target_user = res.scalars().first()
    data = svc.member_to_dict(target, target_user)
    await hub.publish(workspace_id, "member:updated", {"member": data})
    return data


@router.delete("/{workspace_id}/members/{member_id}", status_code=204)
async def delete_member(
    workspace_id: str,
    member_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    requester = await svc.require_role(db, workspace_id, user, ("owner", "admin"))
    res = await db.execute(select(Member).where(Member.id == member_id))
    target = res.scalars().first()
    if target is None or target.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="member not found")
    if target.role == "owner" and requester.role != "owner":
        raise HTTPException(status_code=403, detail="insufficient permissions")
    if target.role == "owner" and await svc.count_owners(db, workspace_id) <= 1:
        raise HTTPException(status_code=400, detail="workspace must have at least one owner")
    await db.delete(target)
    await db.commit()
    await hub.publish(
        workspace_id,
        "member:removed",
        {"member_id": member_id, "workspace_id": workspace_id, "user_id": target.user_id},
    )
    return Response(status_code=204)


@router.post("/{workspace_id}/leave", status_code=204)
async def leave_workspace(
    workspace_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    member = await svc.require_member(db, workspace_id, user)
    if member.role == "owner" and await svc.count_owners(db, workspace_id) <= 1:
        raise HTTPException(status_code=400, detail="workspace must have at least one owner")
    member_id = member.id
    await db.delete(member)
    await db.commit()
    await hub.publish(
        workspace_id,
        "member:removed",
        {"member_id": member_id, "workspace_id": workspace_id, "user_id": user.id},
    )
    return Response(status_code=204)


# ── Convites (workspace-scoped) ───────────────────────────────────────
@router.post("/{workspace_id}/members", status_code=201)
async def create_invitation(
    workspace_id: str,
    body: MemberInviteIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    requester = await svc.require_role(db, workspace_id, user, ("owner", "admin"))
    email = body.email.strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email is required")
    role = body.role.strip() or "member"
    if role not in ("admin", "member"):
        if role == "owner":
            raise HTTPException(status_code=400, detail="cannot invite as owner")
        raise HTTPException(status_code=400, detail="invalid member role")

    # já é membro?
    res = await db.execute(select(User).where(User.email == email))
    existing_user = res.scalars().first()
    if existing_user is not None:
        if await svc.get_member(db, workspace_id, existing_user.id) is not None:
            raise HTTPException(status_code=409, detail="user is already a member")

    # expira pendentes vencidos antes de checar pendência (multica #2055)
    await svc.expire_stale_invitations(db, workspace_id=workspace_id, invitee_email=email)
    res = await db.execute(
        select(Invitation).where(
            Invitation.workspace_id == workspace_id,
            Invitation.invitee_email == email,
            Invitation.status == "pending",
        )
    )
    if res.scalars().first() is not None:
        raise HTTPException(status_code=409, detail="invitation already pending for this email")

    inv = svc.new_invitation(
        workspace_id, requester.user_id, email, role,
        existing_user.id if existing_user else None,
    )
    db.add(inv)
    await db.commit()
    data = svc.invitation_to_dict(inv)

    ws = await _load_workspace(db, workspace_id)
    await hub.publish(
        workspace_id, "invitation:created", {"invitation": data, "workspace_name": ws.name}
    )

    # e-mail de convite (best-effort)
    from ryu.services.email import get_email_service

    try:
        await get_email_service().send_invitation_email(email, user.name or user.email, ws.name, inv.id)
    except Exception as exc:  # noqa: BLE001
        log.warning("invitation_email_failed", email=email, error=str(exc))

    return data


@router.get("/{workspace_id}/invitations")
async def list_workspace_invitations(
    workspace_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.require_member(db, workspace_id, user)
    await svc.expire_stale_invitations(db, workspace_id=workspace_id)
    await db.commit()
    res = await db.execute(
        select(Invitation, User)
        .join(User, User.id == Invitation.inviter_id)
        .where(Invitation.workspace_id == workspace_id, Invitation.status == "pending")
        .order_by(Invitation.created_at.desc())
    )
    return [
        svc.invitation_to_dict(inv, {"inviter_name": u.name, "inviter_email": u.email})
        for inv, u in res.all()
    ]


@router.delete("/{workspace_id}/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(
    workspace_id: str,
    invitation_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.require_role(db, workspace_id, user, ("owner", "admin"))
    res = await db.execute(select(Invitation).where(Invitation.id == invitation_id))
    inv = res.scalars().first()
    if inv is None or inv.workspace_id != workspace_id or inv.status != "pending":
        raise HTTPException(status_code=404, detail="invitation not found")
    inv.status = "revoked"
    await db.commit()
    await hub.publish(
        workspace_id,
        "invitation:revoked",
        {"invitation_id": inv.id, "invitee_email": inv.invitee_email},
    )
    return Response(status_code=204)


# ── Convites (user-scoped: /api/invitations) ──────────────────────────
def _invitation_belongs_to(inv: Invitation, user: User) -> bool:
    return inv.invitee_email == user.email.lower() or inv.invitee_user_id == user.id


async def _load_my_invitation(db: AsyncSession, invitation_id: str, user: User) -> Invitation:
    res = await db.execute(select(Invitation).where(Invitation.id == invitation_id))
    inv = res.scalars().first()
    if inv is None:
        raise HTTPException(status_code=404, detail="invitation not found")
    if not _invitation_belongs_to(inv, user):
        raise HTTPException(status_code=403, detail="invitation does not belong to you")
    return inv


@invitations_router.get("")
async def list_my_invitations(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    await svc.expire_stale_invitations(db, invitee_email=user.email.lower())
    await db.commit()
    res = await db.execute(
        select(Invitation, Workspace, User)
        .join(Workspace, Workspace.id == Invitation.workspace_id)
        .join(User, User.id == Invitation.inviter_id)
        .where(
            (Invitation.invitee_email == user.email.lower())
            | (Invitation.invitee_user_id == user.id),
            Invitation.status == "pending",
        )
        .order_by(Invitation.created_at.desc())
    )
    return [
        svc.invitation_to_dict(
            inv,
            {"workspace_name": ws.name, "inviter_name": u.name, "inviter_email": u.email},
        )
        for inv, ws, u in res.all()
    ]


@invitations_router.get("/{invitation_id}")
async def get_my_invitation(
    invitation_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    inv = await _load_my_invitation(db, invitation_id, user)
    extra: dict = {}
    res = await db.execute(select(Workspace).where(Workspace.id == inv.workspace_id))
    ws = res.scalars().first()
    if ws is not None:
        extra["workspace_name"] = ws.name
        extra["workspace_slug"] = ws.slug
    res = await db.execute(select(User).where(User.id == inv.inviter_id))
    inviter = res.scalars().first()
    if inviter is not None:
        extra["inviter_name"] = inviter.name
        extra["inviter_email"] = inviter.email
    return svc.invitation_to_dict(inv, extra)


@invitations_router.post("/{invitation_id}/accept")
async def accept_invitation(
    invitation_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    inv = await _load_my_invitation(db, invitation_id, user)
    if inv.status != "pending":
        raise HTTPException(status_code=400, detail="invitation is not pending")
    if svc.invitation_expired(inv):
        inv.status = "expired"
        await db.commit()
        raise HTTPException(status_code=410, detail="invitation has expired")
    if await svc.get_member(db, inv.workspace_id, user.id) is not None:
        raise HTTPException(status_code=409, detail="you are already a member of this workspace")

    inv.status = "accepted"
    inv.invitee_user_id = user.id
    member = Member(workspace_id=inv.workspace_id, user_id=user.id, role=inv.role)
    db.add(member)
    await db.commit()
    data = svc.member_to_dict(member, user)
    await hub.publish(inv.workspace_id, "member:added", {"member": data})
    await hub.publish(
        inv.workspace_id,
        "invitation:accepted",
        {"invitation_id": inv.id, "member": data},
    )
    return data


@invitations_router.post("/{invitation_id}/decline", status_code=204)
async def decline_invitation(
    invitation_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    inv = await _load_my_invitation(db, invitation_id, user)
    if inv.status != "pending":
        raise HTTPException(status_code=400, detail="invitation is not pending")
    inv.status = "declined"
    inv.invitee_user_id = user.id
    await db.commit()
    await hub.publish(
        inv.workspace_id,
        "invitation:declined",
        {"invitation_id": inv.id, "invitee_email": inv.invitee_email},
    )
    return Response(status_code=204)


# ── Páginas HTML ──────────────────────────────────────────────────────
@pages_router.get("/w/{slug}/members", response_class=HTMLResponse)
async def members_page(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await current_workspace(slug, db, user)
    me = await svc.get_member(db, ws.id, user.id)
    res = await db.execute(
        select(Member, User)
        .join(User, User.id == Member.user_id)
        .where(Member.workspace_id == ws.id)
        .order_by(Member.created_at)
    )
    members = [(m, u) for m, u in res.all()]
    await svc.expire_stale_invitations(db, workspace_id=ws.id)
    await db.commit()
    res = await db.execute(
        select(Invitation)
        .where(Invitation.workspace_id == ws.id, Invitation.status == "pending")
        .order_by(Invitation.created_at.desc())
    )
    invitations = list(res.scalars())
    return templates.TemplateResponse(
        "workspace/members.html",
        {
            "request": request,
            "user": user,
            "workspace": ws,
            "active_nav": "members",
            "members": members,
            "invitations": invitations,
            "my_role": me.role if me else "member",
            "is_admin": bool(me and me.role in ("owner", "admin")),
        },
    )


@pages_router.get("/invite/{invitation_id}", response_class=HTMLResponse)
async def invite_page(invitation_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Deep-link do e-mail de convite: redireciona p/ login ou mostra o convite."""
    from ryu.services.auth import optional_user

    user = await optional_user(request, db)
    if user is None:
        return RedirectResponse(f"/login?next=/invite/{invitation_id}", status_code=303)
    res = await db.execute(select(Invitation).where(Invitation.id == invitation_id))
    inv = res.scalars().first()
    if inv is None or not _invitation_belongs_to(inv, user):
        raise HTTPException(status_code=404, detail="invitation not found")
    res = await db.execute(select(Workspace).where(Workspace.id == inv.workspace_id))
    ws = res.scalars().first()
    return templates.TemplateResponse(
        "workspace/invite.html",
        {
            "request": request,
            "user": user,
            "invitation": inv,
            "invite_workspace": ws,
            "expired": svc.invitation_expired(inv),
        },
    )
