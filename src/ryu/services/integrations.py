"""Serviço de INTEGRATIONS — GitHub App, VCS self-hosted (Forgejo/Gitea/
GitLab), canais Slack/Lark e o pipeline de espelhamento de PR/CI.

Cada integração externa é código completo, ativado por configuração
(env var RYU_* ou registro BYO no banco). Sem configuração: no-op com log
claro (nunca crasha, nunca finge sucesso).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.config import settings
from ryu.models import (
    ChannelChatLink,
    ChannelInboundAudit,
    ChannelInboundDedup,
    ChannelInstallation,
    ChannelUserBinding,
    ChatSession,
    GithubCheckRun,
    GithubInstallation,
    GithubPullRequest,
    Issue,
    IssuePullRequest,
    VcsConnection,
    VcsPullRequest,
    uid,
)
from ryu.realtime.hub import hub
from ryu.services.crypto import decrypt_secret, encrypt_secret, verify_hmac_sha256

log = structlog.get_logger("ryu.integrations")


class IntegrationError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def now() -> datetime:
    return datetime.now(timezone.utc)


# ── GitHub App ──────────────────────────────────────────────────────────
def github_app_configured() -> bool:
    return bool(settings.github_app_id)


def github_install_url() -> str:
    """URL pública p/ o fluxo de instalação do GitHub App (redirect)."""
    if not github_app_configured():
        raise IntegrationError("GitHub App não configurado (RYU_GITHUB_APP_ID)", 503)
    slug = settings.github_app_slug or settings.github_app_id
    return f"https://github.com/apps/{slug}/installations/new"


async def upsert_github_installation(
    db: AsyncSession, *, workspace_id: str, installation_id: str, account_login: str,
    account_type: str, installed_by: str | None = None,
) -> GithubInstallation:
    row = (
        await db.execute(
            select(GithubInstallation).where(GithubInstallation.installation_id == installation_id)
        )
    ).scalar_one_or_none()
    if row is None:
        row = GithubInstallation(
            id=uid(), workspace_id=workspace_id, installation_id=installation_id,
        )
        db.add(row)
    row.account_login = account_login
    row.account_type = account_type
    row.status = "active"
    if installed_by:
        row.installed_by = installed_by
    await db.commit()
    await db.refresh(row)
    return row


async def list_github_installations(db: AsyncSession, workspace_id: str) -> list[GithubInstallation]:
    rows = await db.execute(
        select(GithubInstallation).where(GithubInstallation.workspace_id == workspace_id)
    )
    return list(rows.scalars())


async def remove_github_installation(db: AsyncSession, workspace_id: str, installation_id: str) -> None:
    row = (
        await db.execute(
            select(GithubInstallation).where(
                GithubInstallation.workspace_id == workspace_id,
                GithubInstallation.installation_id == installation_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise IntegrationError("installation não encontrada", 404)
    row.status = "removed"
    await db.commit()


def verify_github_signature(secret: str | None, body: bytes, signature_header: str | None) -> bool:
    if not secret:
        # gate do multica: sem secret configurado, endpoint recusa (503 tratado no router)
        return False
    if not signature_header:
        return False
    return verify_hmac_sha256(secret, body, signature_header, prefix="sha256=")


_ISSUE_REF_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+([A-Z][A-Z0-9]{1,9}-\d+)\b", re.IGNORECASE
)
_BARE_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b")


async def _find_issue_by_key(db: AsyncSession, workspace_id: str, key: str) -> Issue | None:
    row = (
        await db.execute(
            select(Issue).where(Issue.workspace_id == workspace_id, Issue.key == key.upper())
        )
    ).scalar_one_or_none()
    return row


async def auto_link_issue_pr(
    db: AsyncSession, *, workspace_id: str, provider: str, pr_ref: str, title: str, body: str,
) -> list[str]:
    """Varre title+body por menções tipo "closes RYU-123" (ou apenas RYU-123)
    e cria vínculo IssuePullRequest (dedupe por unique constraint)."""
    text = f"{title}\n{body or ''}"
    keys = {m.group(1).upper() for m in _ISSUE_REF_RE.finditer(text)}
    if not keys:
        keys = {m.group(1).upper() for m in _BARE_KEY_RE.finditer(text)}
    linked: list[str] = []
    for key in keys:
        issue = await _find_issue_by_key(db, workspace_id, key)
        if issue is None:
            continue
        existing = (
            await db.execute(
                select(IssuePullRequest).where(
                    IssuePullRequest.issue_id == issue.id,
                    IssuePullRequest.provider == provider,
                    IssuePullRequest.pull_request_ref == pr_ref,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                IssuePullRequest(
                    id=uid(), issue_id=issue.id, provider=provider,
                    pull_request_ref=pr_ref, link_kind="auto",
                )
            )
            await db.commit()
        linked.append(issue.id)
    return linked


async def mark_linked_issues_done(db: AsyncSession, *, provider: str, pr_ref: str) -> list[str]:
    """merge→done: ao mergear o PR, move todas as issues vinculadas p/ done."""
    rows = (
        await db.execute(
            select(IssuePullRequest).where(
                IssuePullRequest.provider == provider, IssuePullRequest.pull_request_ref == pr_ref
            )
        )
    ).scalars()
    done_ids: list[str] = []
    for link in rows:
        issue = await db.get(Issue, link.issue_id)
        if issue and issue.status != "done":
            issue.status = "done"
            await db.commit()
            await hub.publish(issue.workspace_id, "issue:updated", {"id": issue.id, "status": "done"})
            done_ids.append(issue.id)
    return done_ids


async def upsert_github_pull_request(
    db: AsyncSession, *, workspace_id: str, installation_id: str, repo_full_name: str,
    number: int, title: str, state: str, draft: bool, merged: bool, head_sha: str,
    head_ref: str = "", base_ref: str = "", mergeable: bool | None = None,
    author_login: str = "", url: str = "", body: str = "",
) -> GithubPullRequest:
    row = (
        await db.execute(
            select(GithubPullRequest).where(
                GithubPullRequest.installation_id == installation_id,
                GithubPullRequest.repo_full_name == repo_full_name,
                GithubPullRequest.number == number,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = GithubPullRequest(
            id=uid(), workspace_id=workspace_id, installation_id=installation_id,
            repo_full_name=repo_full_name, number=number,
        )
        db.add(row)
    row.title = title
    row.state = state
    row.draft = draft
    row.merged = merged
    row.head_sha = head_sha
    row.head_ref = head_ref or row.head_ref
    row.base_ref = base_ref or row.base_ref
    row.mergeable = mergeable
    row.author_login = author_login or row.author_login
    row.url = url or row.url
    row.last_synced_at = now()
    await db.commit()
    await db.refresh(row)

    await auto_link_issue_pr(
        db, workspace_id=workspace_id, provider="github", pr_ref=row.id, title=title, body=body
    )
    if merged:
        await mark_linked_issues_done(db, provider="github", pr_ref=row.id)
    await hub.publish(
        workspace_id, "github_pr:updated",
        {"id": row.id, "repo": repo_full_name, "number": number, "state": state, "merged": merged},
    )
    return row


def github_pull_request_to_dict(row: GithubPullRequest, checks: list[GithubCheckRun] | None = None) -> dict:
    repo_owner, _, repo_name = row.repo_full_name.partition("/")
    return {
        "id": row.id,
        "provider": "github",
        "workspace_id": row.workspace_id,
        "repo_owner": repo_owner,
        "repo_name": repo_name or row.repo_full_name,
        "number": row.number,
        "title": row.title,
        "state": row.state,
        "draft": row.draft,
        "merged": row.merged,
        "html_url": row.url,
        "branch": row.head_ref or None,
        "author_login": row.author_login or None,
        "mergeable_state": (
            None if row.mergeable is None else ("mergeable" if row.mergeable else "conflicting")
        ),
        "pr_created_at": row.created_at.isoformat() if row.created_at else None,
        "pr_updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "checks": [
            {
                "id": c.id,
                "external_id": c.external_id,
                "name": c.name,
                "status": c.status,
                "conclusion": c.conclusion,
            }
            for c in (checks or [])
        ],
    }


def vcs_pull_request_to_dict(row: VcsPullRequest, provider: str) -> dict:
    return {
        "id": row.id,
        "provider": provider,
        "workspace_id": row.workspace_id,
        "connection_id": row.connection_id,
        "number": row.number,
        "title": row.title,
        "state": row.state,
        "draft": row.draft,
        "merged": row.merged,
        "html_url": row.url,
        "branch": None,
        "author_login": None,
        "mergeable_state": None,
        "pr_created_at": row.created_at.isoformat() if row.created_at else None,
        "pr_updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "checks": [],
    }


async def list_pull_requests_for_issue(db: AsyncSession, issue_id: str) -> list[dict]:
    """Lista PRs vinculados a uma issue (github + vcs self-hosted), mais
    recentes primeiro (multica router.go:1112, ListPullRequestsForIssue)."""
    links = (
        await db.execute(select(IssuePullRequest).where(IssuePullRequest.issue_id == issue_id))
    ).scalars().all()
    out: list[dict] = []
    for link in links:
        if link.provider == "github":
            pr = await db.get(GithubPullRequest, link.pull_request_ref)
            if pr is None:
                continue
            checks = (
                await db.execute(
                    select(GithubCheckRun).where(GithubCheckRun.pull_request_id == pr.id)
                )
            ).scalars().all()
            out.append(github_pull_request_to_dict(pr, checks))
        else:
            pr = await db.get(VcsPullRequest, link.pull_request_ref)
            if pr is None:
                continue
            out.append(vcs_pull_request_to_dict(pr, link.provider))
    out.sort(key=lambda d: d["pr_created_at"] or "", reverse=True)
    return out


async def upsert_github_check_run(
    db: AsyncSession, *, pull_request_id: str, external_id: str, name: str, status: str,
    conclusion: str | None, ordinal: int = 0,
) -> GithubCheckRun:
    row = (
        await db.execute(
            select(GithubCheckRun).where(
                GithubCheckRun.pull_request_id == pull_request_id,
                GithubCheckRun.external_id == external_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = GithubCheckRun(id=uid(), pull_request_id=pull_request_id, external_id=external_id)
        db.add(row)
    row.name = name
    row.status = status
    row.conclusion = conclusion
    row.ordinal = ordinal
    await db.commit()
    await db.refresh(row)
    return row


async def fetch_github_pr_snapshot(installation_id: str, repo_full_name: str, number: int) -> dict | None:
    """Busca estado autoritativo (mergeability + checks) via API do GitHub.
    No-op (retorna None) sem app configurado — chamador decide o fallback."""
    if not github_app_configured():
        log.info("github_snapshot_skip_not_configured", repo=repo_full_name, number=number)
        return None
    # Sem geração de JWT/installation token real (exigiria PyJWT — fora do pyproject),
    # então usamos apenas dados já recebidos via webhook; refresh explícito fica
    # marcado como TODO quando uma lib de JWT RS256 estiver disponível.
    log.info("github_snapshot_manual_refresh_unavailable", repo=repo_full_name, number=number)
    return None


# ── VCS self-hosted (Forgejo/Gitea/GitLab) ─────────────────────────────
async def create_vcs_connection(
    db: AsyncSession, *, workspace_id: str, provider: str, base_url: str, repo: str,
    access_token: str, webhook_secret: str, created_by: str,
) -> VcsConnection:
    if provider not in ("forgejo", "gitea", "gitlab"):
        raise IntegrationError(f"provider inválido: {provider}")
    conn = VcsConnection(
        id=uid(), workspace_id=workspace_id, provider=provider, base_url=base_url.rstrip("/"),
        repo=repo, access_token_enc=encrypt_secret(access_token) or "",
        webhook_secret_enc=encrypt_secret(webhook_secret) or "", webhook_token=uuid.uuid4().hex,
        created_by=created_by,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return conn


async def list_vcs_connections(db: AsyncSession, workspace_id: str) -> list[VcsConnection]:
    rows = await db.execute(select(VcsConnection).where(VcsConnection.workspace_id == workspace_id))
    return list(rows.scalars())


async def get_vcs_connection_by_token(db: AsyncSession, webhook_token: str) -> VcsConnection | None:
    row = (
        await db.execute(select(VcsConnection).where(VcsConnection.webhook_token == webhook_token))
    ).scalar_one_or_none()
    return row


async def delete_vcs_connection(db: AsyncSession, workspace_id: str, connection_id: str) -> None:
    conn = await db.get(VcsConnection, connection_id)
    if conn is None or conn.workspace_id != workspace_id:
        raise IntegrationError("conexão não encontrada", 404)
    await db.delete(conn)
    await db.commit()


def verify_vcs_signature(conn: VcsConnection, headers: dict, body: bytes) -> bool:
    secret = decrypt_secret(conn.webhook_secret_enc) or ""
    if not secret:
        return False
    if conn.provider == "gitlab":
        token = headers.get("x-gitlab-token") or headers.get("X-Gitlab-Token")
        return bool(token) and token == secret
    # Forgejo/Gitea: X-Hub-Signature-256 (mesmo formato do GitHub)
    sig = headers.get("x-hub-signature-256") or headers.get("X-Hub-Signature-256")
    return verify_hmac_sha256(secret, body, sig or "", prefix="sha256=")


async def upsert_vcs_pull_request(
    db: AsyncSession, *, connection: VcsConnection, number: int, title: str, state: str,
    draft: bool, merged: bool, head_sha: str, url: str = "", body: str = "",
) -> VcsPullRequest:
    row = (
        await db.execute(
            select(VcsPullRequest).where(
                VcsPullRequest.connection_id == connection.id, VcsPullRequest.number == number
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = VcsPullRequest(
            id=uid(), workspace_id=connection.workspace_id, connection_id=connection.id, number=number
        )
        db.add(row)
    row.title = title
    row.state = state
    row.draft = draft
    row.merged = merged
    row.head_sha = head_sha
    row.url = url or row.url
    row.last_synced_at = now()
    await db.commit()
    await db.refresh(row)

    provider = connection.provider
    await auto_link_issue_pr(
        db, workspace_id=connection.workspace_id, provider=provider, pr_ref=row.id, title=title, body=body
    )
    if merged:
        await mark_linked_issues_done(db, provider=provider, pr_ref=row.id)
    await hub.publish(
        connection.workspace_id, "vcs_pr:updated",
        {"id": row.id, "provider": provider, "number": number, "state": state, "merged": merged},
    )
    return row


# ── Channels (Slack / Lark-Feishu) ──────────────────────────────────────
async def install_channel(
    db: AsyncSession, *, workspace_id: str, channel_type: str, agent_id: str | None,
    external_team_id: str, external_team_name: str, bot_token: str, signing_secret: str,
    app_credential: str = "", region: str = "", installed_by: str | None = None,
) -> ChannelInstallation:
    if channel_type not in ("slack", "lark"):
        raise IntegrationError(f"channel_type inválido: {channel_type}")
    if channel_type == "slack" and not settings.slack_enabled:
        raise IntegrationError("canal Slack desativado (RYU_SLACK_ENABLED=false)", 503)
    if channel_type == "lark" and not settings.lark_enabled:
        raise IntegrationError("canal Lark desativado (RYU_LARK_ENABLED=false)", 503)

    row = (
        await db.execute(
            select(ChannelInstallation).where(
                ChannelInstallation.channel_type == channel_type,
                ChannelInstallation.external_team_id == external_team_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = ChannelInstallation(id=uid(), workspace_id=workspace_id, channel_type=channel_type)
        db.add(row)
    row.workspace_id = workspace_id
    row.agent_id = agent_id
    row.external_team_id = external_team_id
    row.external_team_name = external_team_name
    row.region = region
    row.bot_token_enc = encrypt_secret(bot_token) or ""
    row.signing_secret_enc = encrypt_secret(signing_secret) or ""
    row.app_credential_enc = encrypt_secret(app_credential) or ""
    row.status = "active"
    row.installed_by = installed_by
    await db.commit()
    await db.refresh(row)
    return row


async def list_channel_installations(db: AsyncSession, workspace_id: str, channel_type: str | None = None):
    q = select(ChannelInstallation).where(ChannelInstallation.workspace_id == workspace_id)
    if channel_type:
        q = q.where(ChannelInstallation.channel_type == channel_type)
    rows = await db.execute(q)
    return list(rows.scalars())


async def get_installation_by_team(db: AsyncSession, channel_type: str, external_team_id: str):
    return (
        await db.execute(
            select(ChannelInstallation).where(
                ChannelInstallation.channel_type == channel_type,
                ChannelInstallation.external_team_id == external_team_id,
            )
        )
    ).scalar_one_or_none()


def verify_slack_signature(signing_secret: str, headers: dict, raw_body: bytes) -> bool:
    """Slack v0 signature: HMAC-SHA256("v0:<ts>:<body>", signing_secret)."""
    ts = headers.get("x-slack-request-timestamp") or headers.get("X-Slack-Request-Timestamp")
    sig = headers.get("x-slack-signature") or headers.get("X-Slack-Signature")
    if not ts or not sig or not signing_secret:
        return False
    basestring = f"v0:{ts}:{raw_body.decode(errors='replace')}"
    import hashlib
    import hmac as _hmac

    expected = "v0=" + _hmac.new(signing_secret.encode(), basestring.encode(), hashlib.sha256).hexdigest()
    return _hmac.compare_digest(expected, sig)


async def dedup_inbound(db: AsyncSession, *, channel_type: str, installation_id: str, external_event_id: str) -> bool:
    """Retorna True se o evento é NOVO (deve processar); False se já visto (dup)."""
    if not external_event_id:
        return True
    existing = (
        await db.execute(
            select(ChannelInboundDedup).where(
                ChannelInboundDedup.channel_type == channel_type,
                ChannelInboundDedup.installation_id == installation_id,
                ChannelInboundDedup.external_event_id == external_event_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False
    db.add(
        ChannelInboundDedup(
            id=uid(), channel_type=channel_type, installation_id=installation_id,
            external_event_id=external_event_id,
        )
    )
    await db.commit()
    return True


async def audit_inbound(
    db: AsyncSession, *, channel_type: str, installation_id: str, external_event_id: str = "",
    external_channel_id: str = "", external_user_id: str = "", text: str = "", raw: dict | None = None,
) -> None:
    db.add(
        ChannelInboundAudit(
            id=uid(), channel_type=channel_type, installation_id=installation_id,
            external_event_id=external_event_id, external_channel_id=external_channel_id,
            external_user_id=external_user_id, text=text, raw=raw or {},
        )
    )
    await db.commit()


async def get_or_create_binding(
    db: AsyncSession, *, channel_type: str, installation_id: str, external_user_id: str,
) -> ChannelUserBinding:
    row = (
        await db.execute(
            select(ChannelUserBinding).where(
                ChannelUserBinding.channel_type == channel_type,
                ChannelUserBinding.installation_id == installation_id,
                ChannelUserBinding.external_user_id == external_user_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = ChannelUserBinding(
            id=uid(), channel_type=channel_type, installation_id=installation_id,
            external_user_id=external_user_id, bind_token=uuid.uuid4().hex,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def redeem_binding_token(db: AsyncSession, bind_token: str, user_id: str) -> ChannelUserBinding:
    row = (
        await db.execute(select(ChannelUserBinding).where(ChannelUserBinding.bind_token == bind_token))
    ).scalar_one_or_none()
    if row is None or row.bind_token_used:
        raise IntegrationError("token de binding inválido ou já usado", 404)
    row.user_id = user_id
    row.bind_token_used = True
    await db.commit()
    await db.refresh(row)
    return row


async def get_or_create_chat_link(
    db: AsyncSession, *, channel_type: str, installation_id: str, external_channel_id: str,
    external_thread_id: str, create_session,
) -> ChannelChatLink:
    row = (
        await db.execute(
            select(ChannelChatLink).where(
                ChannelChatLink.channel_type == channel_type,
                ChannelChatLink.installation_id == installation_id,
                ChannelChatLink.external_channel_id == external_channel_id,
                ChannelChatLink.external_thread_id == external_thread_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        session_id = await create_session()
        row = ChannelChatLink(
            id=uid(), channel_type=channel_type, installation_id=installation_id,
            external_channel_id=external_channel_id, external_thread_id=external_thread_id,
            chat_session_id=session_id,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def route_channel_message(
    db: AsyncSession, *, installation: ChannelInstallation, external_channel_id: str,
    external_thread_id: str, user_id: str, text: str,
) -> None:
    """Ponte canal→agente (multica channel/engine/router.go: ensure session →
    append+mark → trigger agent run). Vincula (ou cria) uma chat_session real
    ao thread do canal via get_or_create_chat_link e enfileira a AgentTask —
    a resposta real do agente é entregue de volta ao canal por
    chat.handle_chat_task_done quando a task termina (ver ali)."""
    if not text.strip():
        return
    if not installation.agent_id:
        log.warning("channel_route_no_agent", installation_id=installation.id)
        return

    from ryu.services import chat as chat_svc

    async def _create_session() -> str:
        session = await chat_svc.create_session(
            db, workspace_id=installation.workspace_id, user_id=user_id,
            agent_id=installation.agent_id,
            title=f"{installation.channel_type}: {external_channel_id}"[:60] or "Nova conversa",
        )
        return session.id

    link = await get_or_create_chat_link(
        db, channel_type=installation.channel_type, installation_id=installation.id,
        external_channel_id=external_channel_id,
        external_thread_id=external_thread_id or external_channel_id,
        create_session=_create_session,
    )
    session = await db.get(ChatSession, link.chat_session_id)
    if session is None or session.archived:
        log.warning("channel_route_session_unavailable", installation_id=installation.id)
        return
    await chat_svc.add_user_message(db, session, text)


def markdown_to_mrkdwn(text: str) -> str:
    """Conversão simples markdown → mrkdwn do Slack (bold/italic/links)."""
    out = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    out = re.sub(r"(?<!\*)\*(?!\*)([^*]+)\*(?!\*)", r"_\1_", out)
    out = re.sub(r"\[(.+?)\]\((.+?)\)", r"<\2|\1>", out)
    return out


async def send_slack_message(installation: ChannelInstallation, channel: str, text: str, thread_ts: str | None = None) -> dict:
    token = decrypt_secret(installation.bot_token_enc)
    if not token:
        log.warning("slack_send_no_token", installation_id=installation.id)
        return {"ok": False, "error": "no_token_configured"}
    payload = {"channel": channel, "text": markdown_to_mrkdwn(text)}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{settings.slack_api_base_url}/chat.postMessage",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
        return r.json()
    except Exception as e:
        log.error("slack_send_failed", error=str(e))
        return {"ok": False, "error": str(e)}


async def send_lark_message(installation: ChannelInstallation, receive_id: str, text: str) -> dict:
    token = decrypt_secret(installation.bot_token_enc)
    if not token:
        log.warning("lark_send_no_token", installation_id=installation.id)
        return {"ok": False, "error": "no_token_configured"}
    base = "https://open.larksuite.com" if installation.region == "larksuite" else "https://open.feishu.cn"
    try:
        import json as _json

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{base}/open-apis/im/v1/messages?receive_id_type=chat_id",
                json={"receive_id": receive_id, "msg_type": "text", "content": _json.dumps({"text": text})},
                headers={"Authorization": f"Bearer {token}"},
            )
        return r.json()
    except Exception as e:
        log.error("lark_send_failed", error=str(e))
        return {"ok": False, "error": str(e)}
