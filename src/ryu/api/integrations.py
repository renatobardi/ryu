"""API do domínio INTEGRATIONS.

- `router`: rotas autenticadas de gestão (GitHub installations, VCS
  connections, channel installations), montar em main.py com
  prefix="/api/integrations".
- `webhooks_router`: ingress público (sem auth de sessão), montar SEM
  prefixo — já expõe os paths completos (/api/webhooks/...).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.config import settings
from ryu.db import get_db
from ryu.models import ChannelInstallation, GithubInstallation, GithubPullRequest, User, VcsConnection, Workspace
from ryu.services import integrations as svc
from ryu.services.auth import current_user
from ryu.services.crypto import mask_secret

router = APIRouter()
webhooks_router = APIRouter()


def _err(e: svc.IntegrationError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=e.message)


async def _member_of(db: AsyncSession, workspace_id: str, user: User) -> Workspace:
    ws = await db.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(404, "workspace não encontrado")
    return ws


# ── GitHub App ──────────────────────────────────────────────────────────
@router.get("/github/connect")
async def github_connect(workspace_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await _member_of(db, workspace_id, user)
    try:
        url = svc.github_install_url()
    except svc.IntegrationError as e:
        raise _err(e)
    return {"install_url": url, "state": workspace_id}


@router.get("/github/installations")
async def github_installations(workspace_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await _member_of(db, workspace_id, user)
    rows = await svc.list_github_installations(db, workspace_id)
    return [
        {
            "id": r.id, "installation_id": r.installation_id, "account_login": r.account_login,
            "account_type": r.account_type, "status": r.status,
        }
        for r in rows
    ]


@router.delete("/github/installations/{installation_id}", status_code=204)
async def github_installation_delete(
    workspace_id: str, installation_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    await _member_of(db, workspace_id, user)
    try:
        await svc.remove_github_installation(db, workspace_id, installation_id)
    except svc.IntegrationError as e:
        raise _err(e)


@webhooks_router.post("/api/webhooks/github")
async def github_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.github_webhook_secret:
        raise HTTPException(503, "GitHub webhook não configurado (RYU_GITHUB_WEBHOOK_SECRET)")
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256")
    if not svc.verify_github_signature(settings.github_webhook_secret, body, sig):
        raise HTTPException(401, "assinatura inválida")

    event = request.headers.get("X-GitHub-Event", "")
    payload: dict[str, Any] = await request.json()
    installation = payload.get("installation") or {}
    installation_id = str(installation.get("id") or "")

    if event == "installation":
        action = payload.get("action")
        account = payload.get("installation", {}).get("account", {})
        row = (
            await db.execute(
                select(GithubInstallation).where(GithubInstallation.installation_id == installation_id)
            )
        ).scalar_one_or_none()
        if action == "created" and row is None:
            # Sem workspace vinculado ainda (o link real acontece no /connect
            # callback com state=workspace_id); registramos como órfã por ora.
            await svc.upsert_github_installation(
                db, workspace_id="", installation_id=installation_id,
                account_login=account.get("login", ""), account_type=account.get("type", ""),
            )
        elif action in ("deleted", "suspend") and row is not None:
            row.status = "removed" if action == "deleted" else "suspended"
            await db.commit()
        return {"ok": True}

    if event == "pull_request" and installation_id:
        pr = payload.get("pull_request", {})
        gi = (
            await db.execute(
                select(GithubInstallation).where(GithubInstallation.installation_id == installation_id)
            )
        ).scalar_one_or_none()
        workspace_id = gi.workspace_id if gi else ""
        state = "merged" if pr.get("merged") else ("draft" if pr.get("draft") else pr.get("state", "open"))
        await svc.upsert_github_pull_request(
            db, workspace_id=workspace_id, installation_id=installation_id,
            repo_full_name=payload.get("repository", {}).get("full_name", ""),
            number=pr.get("number", 0), title=pr.get("title", ""), state=state,
            draft=bool(pr.get("draft")), merged=bool(pr.get("merged")),
            head_sha=pr.get("head", {}).get("sha", ""), head_ref=pr.get("head", {}).get("ref", ""),
            base_ref=pr.get("base", {}).get("ref", ""), mergeable=pr.get("mergeable"),
            author_login=pr.get("user", {}).get("login", ""), url=pr.get("html_url", ""),
            body=pr.get("body", ""),
        )
        return {"ok": True}

    if event in ("check_run", "check_suite") and installation_id:
        repo = payload.get("repository", {}).get("full_name", "")
        node = payload.get(event, {})
        head_sha = node.get("head_sha", "")
        pr_row = None
        if head_sha:
            rows = await db.execute(
                select(GithubPullRequest).where(
                    GithubPullRequest.repo_full_name == repo,
                    GithubPullRequest.head_sha == head_sha,
                )
            )
            pr_row = rows.scalars().first()
        if pr_row is not None:
            await svc.upsert_github_check_run(
                db, pull_request_id=pr_row.id, external_id=str(node.get("id", "")),
                name=node.get("name", node.get("app", {}).get("name", "")),
                status=node.get("status", "queued"), conclusion=node.get("conclusion"),
            )
        return {"ok": True}

    return {"ok": True, "ignored": event}


# ── VCS self-hosted (Forgejo/Gitea/GitLab) ─────────────────────────────
class VcsConnectionCreate(BaseModel):
    workspace_id: str
    provider: str
    base_url: str
    repo: str
    access_token: str
    webhook_secret: str


@router.post("/vcs/connections", status_code=201)
async def vcs_create(payload: VcsConnectionCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await _member_of(db, payload.workspace_id, user)
    try:
        conn = await svc.create_vcs_connection(
            db, workspace_id=payload.workspace_id, provider=payload.provider, base_url=payload.base_url,
            repo=payload.repo, access_token=payload.access_token, webhook_secret=payload.webhook_secret,
            created_by=user.id,
        )
    except svc.IntegrationError as e:
        raise _err(e)
    return _vcs_dict(conn)


def _vcs_dict(c: VcsConnection) -> dict:
    return {
        "id": c.id, "provider": c.provider, "base_url": c.base_url, "repo": c.repo,
        "status": c.status, "webhook_url": f"/api/webhooks/vcs/{c.webhook_token}",
    }


@router.get("/vcs/connections")
async def vcs_list(workspace_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await _member_of(db, workspace_id, user)
    rows = await svc.list_vcs_connections(db, workspace_id)
    return [_vcs_dict(r) for r in rows]


@router.delete("/vcs/connections/{connection_id}", status_code=204)
async def vcs_delete(
    workspace_id: str, connection_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    await _member_of(db, workspace_id, user)
    try:
        await svc.delete_vcs_connection(db, workspace_id, connection_id)
    except svc.IntegrationError as e:
        raise _err(e)


@webhooks_router.post("/api/webhooks/vcs/{webhook_token}")
async def vcs_webhook(webhook_token: str, request: Request, db: AsyncSession = Depends(get_db)):
    conn = await svc.get_vcs_connection_by_token(db, webhook_token)
    if conn is None:
        raise HTTPException(404, "conexão não encontrada")
    body = await request.body()
    if not svc.verify_vcs_signature(conn, dict(request.headers), body):
        raise HTTPException(401, "assinatura/secret inválido")
    payload = await request.json()

    if conn.provider == "gitlab":
        mr = payload.get("object_attributes", {})
        number = mr.get("iid", 0)
        state = mr.get("state", "open")
        merged = state == "merged"
        title = mr.get("title", "")
        body_text = mr.get("description", "")
        head_sha = mr.get("last_commit", {}).get("id", "")
        url = mr.get("url", "")
        draft = bool(mr.get("draft") or mr.get("work_in_progress"))
    else:  # forgejo | gitea
        pr = payload.get("pull_request", {})
        number = pr.get("number", 0)
        merged = bool(pr.get("merged"))
        state = "merged" if merged else pr.get("state", "open")
        title = pr.get("title", "")
        body_text = pr.get("body", "")
        head_sha = pr.get("head", {}).get("sha", "")
        url = pr.get("html_url", pr.get("url", ""))
        draft = bool(pr.get("draft"))

    if number:
        await svc.upsert_vcs_pull_request(
            db, connection=conn, number=number, title=title, state=state, draft=draft,
            merged=merged, head_sha=head_sha, url=url, body=body_text,
        )
    return {"ok": True}


# ── Channels (Slack / Lark) ─────────────────────────────────────────────
class ChannelInstall(BaseModel):
    workspace_id: str
    channel_type: str  # slack|lark
    agent_id: str | None = None
    external_team_id: str
    external_team_name: str = ""
    bot_token: str
    signing_secret: str = ""
    app_credential: str = ""
    region: str = ""  # lark: feishu|larksuite


def _channel_dict(c: ChannelInstallation) -> dict:
    return {
        "id": c.id, "channel_type": c.channel_type, "external_team_id": c.external_team_id,
        "external_team_name": c.external_team_name, "status": c.status, "region": c.region,
        "agent_id": c.agent_id,
    }


@router.post("/channels/install", status_code=201)
async def channel_install(payload: ChannelInstall, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await _member_of(db, payload.workspace_id, user)
    try:
        row = await svc.install_channel(
            db, workspace_id=payload.workspace_id, channel_type=payload.channel_type,
            agent_id=payload.agent_id, external_team_id=payload.external_team_id,
            external_team_name=payload.external_team_name, bot_token=payload.bot_token,
            signing_secret=payload.signing_secret, app_credential=payload.app_credential,
            region=payload.region, installed_by=user.id,
        )
    except svc.IntegrationError as e:
        raise _err(e)
    return _channel_dict(row)


@router.get("/channels")
async def channels_list(workspace_id: str, channel_type: str | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await _member_of(db, workspace_id, user)
    rows = await svc.list_channel_installations(db, workspace_id, channel_type)
    return [_channel_dict(r) for r in rows]


@router.post("/channels/bind/{bind_token}")
async def channel_bind(bind_token: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    try:
        row = await svc.redeem_binding_token(db, bind_token, user.id)
    except svc.IntegrationError as e:
        raise _err(e)
    return {"ok": True, "external_user_id": row.external_user_id}


@webhooks_router.post("/api/webhooks/slack")
async def slack_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.slack_enabled:
        raise HTTPException(503, "canal Slack desativado")
    body = await request.body()
    payload = await request.json()

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    team_id = payload.get("team_id", "")
    installation = await svc.get_installation_by_team(db, "slack", team_id)
    if installation is None:
        raise HTTPException(404, "installation Slack não encontrada")

    from ryu.services.crypto import decrypt_secret

    secret = decrypt_secret(installation.signing_secret_enc) or ""
    if not svc.verify_slack_signature(secret, dict(request.headers), body):
        raise HTTPException(401, "assinatura inválida")

    event_id = payload.get("event_id", "")
    is_new = await svc.dedup_inbound(
        db, channel_type="slack", installation_id=installation.id, external_event_id=event_id
    )
    event = payload.get("event", {})
    await svc.audit_inbound(
        db, channel_type="slack", installation_id=installation.id, external_event_id=event_id,
        external_channel_id=event.get("channel", ""), external_user_id=event.get("user", ""),
        text=event.get("text", ""), raw=payload,
    )
    if not is_new:
        return {"ok": True, "dedup": True}

    if event.get("type") == "message" and event.get("user") and not event.get("bot_id"):
        binding = await svc.get_or_create_binding(
            db, channel_type="slack", installation_id=installation.id, external_user_id=event["user"]
        )
        if not binding.user_id:
            bind_url = f"{settings.app_url or ''}/integrations/bind/{binding.bind_token}"
            await svc.send_slack_message(
                installation, event.get("channel", ""),
                f"Para eu responder, vincule sua conta Ryu: {bind_url}",
            )
        else:
            # eco simples — o roteamento real p/ o agente/chat_session fica a
            # cargo do serviço de chat (fora deste domínio); aqui garantimos
            # dedup + audit + resposta mínima.
            await svc.send_slack_message(
                installation, event.get("channel", ""), "Recebido — processando…",
            )
    return {"ok": True}


@webhooks_router.post("/api/webhooks/lark")
async def lark_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.lark_enabled:
        raise HTTPException(503, "canal Lark desativado")
    payload = await request.json()

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    header = payload.get("header", {})
    team_id = header.get("tenant_key", "") or header.get("app_id", "")
    installation = await svc.get_installation_by_team(db, "lark", team_id)
    if installation is None:
        raise HTTPException(404, "installation Lark não encontrada")

    event_id = header.get("event_id", "")
    is_new = await svc.dedup_inbound(
        db, channel_type="lark", installation_id=installation.id, external_event_id=event_id
    )
    event = payload.get("event", {})
    sender = event.get("sender", {}).get("sender_id", {}).get("open_id", "")
    msg = event.get("message", {})
    await svc.audit_inbound(
        db, channel_type="lark", installation_id=installation.id, external_event_id=event_id,
        external_channel_id=msg.get("chat_id", ""), external_user_id=sender, text=msg.get("content", ""),
        raw=payload,
    )
    if not is_new:
        return {"ok": True, "dedup": True}

    if sender:
        binding = await svc.get_or_create_binding(
            db, channel_type="lark", installation_id=installation.id, external_user_id=sender
        )
        if not binding.user_id:
            bind_url = f"{settings.app_url or ''}/integrations/bind/{binding.bind_token}"
            await svc.send_lark_message(installation, msg.get("chat_id", ""), f"Vincule sua conta Ryu: {bind_url}")
        else:
            await svc.send_lark_message(installation, msg.get("chat_id", ""), "Recebido — processando…")
    return {"ok": True}
