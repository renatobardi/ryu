"""Testes do domínio integrations: HMAC do webhook GitHub e espelhamento
de PR (upsert, auto-link issue↔PR via texto, merge→done)."""
from __future__ import annotations

import hashlib
import hmac
import json

import httpx

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


# ── Authz de workspace ───────────────────────────────────────────────
async def test_integrations_reject_non_member(client):
    _, ws = await _setup(client, "integr-owner@ryu.dev")
    await login(client, "integr-outsider@ryu.dev")  # sem membership no ws acima

    r = await client.get("/api/integrations/github/installations", params={"workspace_id": ws["id"]})
    assert r.status_code == 403, r.text

    r = await client.get("/api/integrations/vcs/connections", params={"workspace_id": ws["id"]})
    assert r.status_code == 403, r.text

    r = await client.get("/api/integrations/channels", params={"workspace_id": ws["id"]})
    assert r.status_code == 403, r.text

    r = await client.post(
        "/api/integrations/vcs/connections",
        json={
            "workspace_id": ws["id"], "provider": "forgejo", "base_url": "https://git.example",
            "repo": "acme/repo", "access_token": "t", "webhook_secret": "s",
        },
    )
    assert r.status_code == 403, r.text


async def test_integrations_allow_member(client):
    _, ws = await _setup(client, "integr-member@ryu.dev")
    r = await client.get("/api/integrations/vcs/connections", params={"workspace_id": ws["id"]})
    assert r.status_code == 200, r.text


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
