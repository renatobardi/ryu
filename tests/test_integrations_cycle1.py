"""Testes do domínio integrations: HMAC do webhook GitHub e espelhamento
de PR (upsert, auto-link issue↔PR via texto, merge→done)."""
from __future__ import annotations

import hashlib
import hmac
import json

import httpx
from sqlalchemy import select

from .conftest import login


async def _setup(client: httpx.AsyncClient, email: str = "integrations@ryu.dev"):
    data = await login(client, email)
    ws = data["workspaces"][0]
    return data["user"], ws


async def _create_issue(client, ws_id, title="Issue base", **kw):
    r = await client.post("/api/issues", json={"workspace_id": ws_id, "title": title, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ── Webhook HMAC ─────────────────────────────────────────────────────
async def test_github_webhook_503_when_not_configured(client, monkeypatch):
    from ryu.config import settings

    monkeypatch.setattr(settings, "github_webhook_secret", None)
    r = await client.post(
        "/api/webhooks/github",
        content=b"{}",
        headers={"X-GitHub-Event": "ping"},
    )
    assert r.status_code == 503


async def test_github_webhook_rejects_bad_signature(client, monkeypatch):
    from ryu.config import settings

    monkeypatch.setattr(settings, "github_webhook_secret", "topsecret")
    body = b'{"zen": "hi"}'
    r = await client.post(
        "/api/webhooks/github",
        content=body,
        headers={"X-GitHub-Event": "ping", "X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert r.status_code == 401


async def test_github_webhook_accepts_valid_signature(client, monkeypatch):
    from ryu.config import settings

    monkeypatch.setattr(settings, "github_webhook_secret", "topsecret")
    body = json.dumps({"zen": "hi"}).encode()
    sig = _sign("topsecret", body)
    r = await client.post(
        "/api/webhooks/github",
        content=body,
        headers={"X-GitHub-Event": "ping", "X-Hub-Signature-256": sig},
    )
    assert r.status_code == 200
    assert r.json()["ignored"] == "ping"


# ── Espelhamento de PR + auto-link + merge→done ─────────────────────
async def test_github_pr_mirror_autolink_and_merge_done(client, monkeypatch):
    from ryu.config import settings
    from ryu.db import SessionLocal
    from ryu.services import integrations as svc

    monkeypatch.setattr(settings, "github_webhook_secret", "topsecret")

    user, ws = await _setup(client)
    issue = await _create_issue(client, ws["id"], "Corrigir bug de login")
    key = issue["key"]

    # registra installation vinculada ao workspace (normalmente feita no /connect)
    async with SessionLocal() as db:
        await svc.upsert_github_installation(
            db, workspace_id=ws["id"], installation_id="12345",
            account_login="acme", account_type="Organization",
        )

    def _pr_payload(action: str, merged: bool = False, state: str = "open"):
        return {
            "action": action,
            "installation": {"id": 12345},
            "repository": {"full_name": "acme/repo"},
            "pull_request": {
                "number": 7,
                "title": f"Fix login (closes {key})",
                "body": "detalhes",
                "state": state,
                "draft": False,
                "merged": merged,
                "head": {"sha": "abc123", "ref": "fix-login"},
                "base": {"ref": "main"},
                "mergeable": True,
                "user": {"login": "octocat"},
                "html_url": "https://github.com/acme/repo/pull/7",
            },
        }

    body = json.dumps(_pr_payload("opened")).encode()
    r = await client.post(
        "/api/webhooks/github",
        content=body,
        headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": _sign("topsecret", body)},
    )
    assert r.status_code == 200, r.text

    # issue segue aberta, mas já linkada
    r = await client.get(f"/api/issues/{issue['id']}")
    assert r.status_code == 200
    assert r.json()["status"] != "done"

    # merge → done
    body = json.dumps(_pr_payload("closed", merged=True, state="closed")).encode()
    r = await client.post(
        "/api/webhooks/github",
        content=body,
        headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": _sign("topsecret", body)},
    )
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/issues/{issue['id']}")
    assert r.status_code == 200
    assert r.json()["status"] == "done"


# ── Canal Slack/Lark → agent chat routing (bridge viva) ─────────────
def _slack_sig(secret: str, ts: str, body: bytes) -> str:
    basestring = f"v0:{ts}:{body.decode()}"
    return "v0=" + hmac.new(secret.encode(), basestring.encode(), hashlib.sha256).hexdigest()


async def test_slack_message_routes_to_agent_and_replies_in_thread(client, monkeypatch):
    from ryu.runner.loop import _run_one
    from ryu.services import integrations as svc

    user, ws = await _setup(client, "slack-route@example.com")

    r = await client.post(
        "/api/agents",
        json={
            "workspace_id": ws["id"], "name": "SlackBot", "handle": "slackbot",
            "runtime": "echo-fallback",
        },
    )
    assert r.status_code == 201, r.text
    agent = r.json()

    r = await client.post(
        "/api/integrations/channels/install",
        json={
            "workspace_id": ws["id"], "channel_type": "slack", "agent_id": agent["id"],
            "external_team_id": "T123", "external_team_name": "Acme",
            "bot_token": "xoxb-fake", "signing_secret": "shhh",
        },
    )
    assert r.status_code == 201, r.text

    sent: list[dict] = []

    async def _fake_send_slack(installation, channel, text, thread_ts=None):
        sent.append({"channel": channel, "text": text, "thread_ts": thread_ts})
        return {"ok": True}

    monkeypatch.setattr(svc, "send_slack_message", _fake_send_slack)

    def _event_body(user_id: str = "U1") -> bytes:
        return json.dumps(
            {
                "team_id": "T123",
                "event": {"type": "message", "user": user_id, "channel": "C1", "ts": "111.1", "text": "oi agente"},
                "event_id": f"ev-{user_id}-{len(sent)}",
            }
        ).encode()

    # 1ª mensagem: usuário externo ainda não vinculado → recebe link de bind, sem rotear
    body = _event_body()
    ts = "1700000000"
    r = await client.post(
        "/api/webhooks/slack", content=body,
        headers={"x-slack-request-timestamp": ts, "x-slack-signature": _slack_sig("shhh", ts, body)},
    )
    assert r.status_code == 200, r.text
    assert len(sent) == 1
    assert "vincule sua conta" in sent[0]["text"].lower()

    # vincula a conta autenticada ao usuário externo do Slack
    from ryu.db import SessionLocal
    from ryu.models import ChannelUserBinding

    async with SessionLocal() as db:
        binding = (
            await db.execute(
                select(ChannelUserBinding).where(ChannelUserBinding.external_user_id == "U1")
            )
        ).scalar_one()
        bind_token = binding.bind_token

    r = await client.post(f"/api/integrations/channels/bind/{bind_token}")
    assert r.status_code == 200, r.text

    # 2ª mensagem: já vinculado → deve criar chat_session, enfileirar task e,
    # ao terminar, entregar a resposta real do agente de volta ao thread.
    body2 = json.dumps(
        {
            "team_id": "T123",
            "event": {"type": "message", "user": "U1", "channel": "C1", "ts": "222.2", "text": "oi agente de novo"},
            "event_id": "ev-U1-second",
        }
    ).encode()
    r = await client.post(
        "/api/webhooks/slack", content=body2,
        headers={"x-slack-request-timestamp": ts, "x-slack-signature": _slack_sig("shhh", ts, body2)},
    )
    assert r.status_code == 200, r.text

    async with SessionLocal() as db:
        from ryu.models import AgentTask, ChannelChatLink

        link = (
            await db.execute(select(ChannelChatLink).where(ChannelChatLink.installation_id != ""))
        ).scalars().first()
        assert link is not None
        assert link.external_channel_id == "C1"

        task = (
            await db.execute(
                select(AgentTask).where(AgentTask.chat_session_id == link.chat_session_id)
            )
        ).scalars().first()
        assert task is not None
        task_id = task.id

    await _run_one(task_id)

    # a resposta do agente foi entregue de volta ao canal Slack, na thread certa
    assert len(sent) == 2
    assert sent[1]["channel"] == "C1"
    assert sent[1]["thread_ts"] == "222.2"
    assert sent[1]["text"]  # conteúdo real da resposta do agente (echo-fallback)
