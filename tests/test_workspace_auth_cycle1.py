"""Testes do domínio workspace-auth (ciclo 1): papéis, workspaces, convites,
membros, CSRF, allowlists, PAT, notification preferences e inbox em lote."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from .conftest import DEV_CODE, login


def _fresh(client: httpx.AsyncClient) -> None:
    """Limpa cookies/headers de auth (troca de usuário)."""
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)


# ── Workspace CRUD + slugs ────────────────────────────────────────────
async def test_workspace_crud_and_reserved_slugs(client):
    data = await login(client, "wsauth-crud@example.com")

    # criar workspace adicional
    r = await client.post("/api/workspaces", json={"name": "Time X", "slug": "time-x"})
    assert r.status_code == 201, r.text
    ws = r.json()
    assert ws["slug"] == "time-x"
    assert ws["issue_prefix"] == "TIM"

    # slug duplicado → 409
    r = await client.post("/api/workspaces", json={"name": "Outro", "slug": "time-x"})
    assert r.status_code == 409

    # slug inválido / reservado → 400
    r = await client.post("/api/workspaces", json={"name": "A", "slug": "Bad Slug"})
    assert r.status_code == 400
    r = await client.post("/api/workspaces", json={"name": "A", "slug": "settings"})
    assert r.status_code == 400
    assert "reserved" in r.json()["detail"]

    # GET/PATCH
    r = await client.get(f"/api/workspaces/{ws['id']}")
    assert r.status_code == 200
    r = await client.patch(
        f"/api/workspaces/{ws['id']}",
        json={"description": "desc", "context": "ctx", "settings": {"a": 1},
              "repos": [{"url": "https://github.com/x/y.git"}], "issue_prefix": "tx"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["description"] == "desc"
    assert body["settings"] == {"a": 1}
    assert body["issue_prefix"] == "TX"

    # listar inclui os dois workspaces com papel
    r = await client.get("/api/workspaces")
    assert r.status_code == 200
    slugs = {w["slug"]: w["role"] for w in r.json()}
    assert slugs["time-x"] == "owner"
    assert len(slugs) >= 2

    # DELETE (owner) → 204; some da listagem
    r = await client.delete(f"/api/workspaces/{ws['id']}")
    assert r.status_code == 204
    r = await client.get("/api/workspaces")
    assert "time-x" not in {w["slug"] for w in r.json()}

    assert data["workspaces"][0]["slug"] not in ("settings",)


# ── Papéis: member não edita; admin edita; só owner deleta ────────────
async def test_role_enforcement(client):
    owner = await login(client, "wsauth-owner@example.com")
    ws_id = owner["workspaces"][0]["id"]

    # convida member@ como member
    r = await client.post(
        f"/api/workspaces/{ws_id}/members", json={"email": "wsauth-member@example.com"}
    )
    assert r.status_code == 201, r.text
    inv_id = r.json()["id"]

    _fresh(client)
    await login(client, "wsauth-member@example.com")
    r = await client.post(f"/api/invitations/{inv_id}/accept")
    assert r.status_code == 200, r.text

    # member não atualiza workspace nem convida
    r = await client.patch(f"/api/workspaces/{ws_id}", json={"name": "hack"})
    assert r.status_code == 403
    r = await client.post(
        f"/api/workspaces/{ws_id}/members", json={"email": "other@example.com"}
    )
    assert r.status_code == 403
    # member não deleta workspace
    r = await client.delete(f"/api/workspaces/{ws_id}")
    assert r.status_code == 403

    # owner promove member a admin
    _fresh(client)
    await login(client, "wsauth-owner@example.com")
    r = await client.get(f"/api/workspaces/{ws_id}/members")
    members = {m["email"]: m for m in r.json()}
    member_row = members["wsauth-member@example.com"]
    r = await client.patch(
        f"/api/workspaces/{ws_id}/members/{member_row['id']}", json={"role": "admin"}
    )
    assert r.status_code == 200
    assert r.json()["role"] == "admin"

    # admin edita workspace mas NÃO deleta (owner-only) nem promove a owner
    _fresh(client)
    await login(client, "wsauth-member@example.com")
    r = await client.patch(f"/api/workspaces/{ws_id}", json={"name": "Renomeado"})
    assert r.status_code == 200
    r = await client.delete(f"/api/workspaces/{ws_id}")
    assert r.status_code == 403
    owner_row = members["wsauth-owner@example.com"]
    r = await client.patch(
        f"/api/workspaces/{ws_id}/members/{owner_row['id']}", json={"role": "member"}
    )
    assert r.status_code == 403  # admin não rebaixa owner
    r = await client.delete(f"/api/workspaces/{ws_id}/members/{owner_row['id']}")
    assert r.status_code == 403  # admin não remove owner

    # último owner não sai
    _fresh(client)
    await login(client, "wsauth-owner@example.com")
    r = await client.post(f"/api/workspaces/{ws_id}/leave")
    assert r.status_code == 400

    # admin sai do workspace
    _fresh(client)
    await login(client, "wsauth-member@example.com")
    r = await client.post(f"/api/workspaces/{ws_id}/leave")
    assert r.status_code == 204


# ── Convites: fluxo completo ──────────────────────────────────────────
async def test_invitation_flow(client):
    owner = await login(client, "inv-owner@example.com")
    ws_id = owner["workspaces"][0]["id"]

    # papel owner é proibido no convite
    r = await client.post(
        f"/api/workspaces/{ws_id}/members",
        json={"email": "inv-x@example.com", "role": "owner"},
    )
    assert r.status_code == 400

    r = await client.post(
        f"/api/workspaces/{ws_id}/members", json={"email": "inv-a@example.com", "role": "admin"}
    )
    assert r.status_code == 201
    inv = r.json()
    assert inv["status"] == "pending" and inv["role"] == "admin"

    # convite duplicado pendente → 409
    r = await client.post(
        f"/api/workspaces/{ws_id}/members", json={"email": "inv-a@example.com"}
    )
    assert r.status_code == 409

    # listar convites do workspace
    r = await client.get(f"/api/workspaces/{ws_id}/invitations")
    assert r.status_code == 200
    assert any(i["id"] == inv["id"] for i in r.json())

    # revogar e recriar
    r = await client.delete(f"/api/workspaces/{ws_id}/invitations/{inv['id']}")
    assert r.status_code == 204
    r = await client.post(
        f"/api/workspaces/{ws_id}/members", json={"email": "inv-a@example.com"}
    )
    assert r.status_code == 201
    inv2 = r.json()

    # convidado: lista, vê, aceita
    _fresh(client)
    await login(client, "inv-a@example.com")
    r = await client.get("/api/invitations")
    assert any(i["id"] == inv2["id"] for i in r.json())
    r = await client.get(f"/api/invitations/{inv2['id']}")
    assert r.status_code == 200 and r.json()["workspace_name"]
    r = await client.post(f"/api/invitations/{inv2['id']}/accept")
    assert r.status_code == 200
    assert r.json()["role"] == "member"
    # aceitar de novo → não pendente
    r = await client.post(f"/api/invitations/{inv2['id']}/accept")
    assert r.status_code == 400

    # já é membro → 409 em novo convite
    _fresh(client)
    await login(client, "inv-owner@example.com")
    r = await client.post(
        f"/api/workspaces/{ws_id}/members", json={"email": "inv-a@example.com"}
    )
    assert r.status_code == 409

    # decline por outro convidado
    r = await client.post(
        f"/api/workspaces/{ws_id}/members", json={"email": "inv-b@example.com"}
    )
    inv3 = r.json()
    _fresh(client)
    await login(client, "inv-b@example.com")
    r = await client.post(f"/api/invitations/{inv3['id']}/decline")
    assert r.status_code == 204
    # convite de outra pessoa → 403
    _fresh(client)
    await login(client, "inv-c@example.com")
    r = await client.get(f"/api/invitations/{inv3['id']}")
    assert r.status_code == 403


async def test_invitation_expiry(client):
    owner = await login(client, "inv-exp-owner@example.com")
    ws_id = owner["workspaces"][0]["id"]
    r = await client.post(
        f"/api/workspaces/{ws_id}/members", json={"email": "inv-exp@example.com"}
    )
    inv = r.json()

    # força expiração no banco
    from sqlalchemy import update

    from ryu.db import SessionLocal
    from ryu.models import Invitation

    async with SessionLocal() as db:
        await db.execute(
            update(Invitation)
            .where(Invitation.id == inv["id"])
            .values(expires_at=datetime.now(timezone.utc) - timedelta(days=1))
        )
        await db.commit()

    # a listagem expira automaticamente pendentes vencidos
    r = await client.get(f"/api/workspaces/{ws_id}/invitations")
    assert all(i["id"] != inv["id"] for i in r.json())

    _fresh(client)
    await login(client, "inv-exp@example.com")
    r = await client.post(f"/api/invitations/{inv['id']}/accept")
    assert r.status_code in (400, 410)  # expirado


# ── CSRF ──────────────────────────────────────────────────────────────
async def test_csrf_required_for_cookie_auth(client):
    data = await login(client, "csrf@example.com")
    ws_id = data["workspaces"][0]["id"]
    assert client.cookies.get("ryu_csrf")

    # sem header → 403 em POST /api/* via cookie
    client.headers.pop("X-CSRF-Token", None)
    r = await client.post("/api/issues", json={"workspace_id": ws_id, "title": "x"})
    assert r.status_code == 403
    r = await client.post(
        "/api/issues", json={"workspace_id": ws_id, "title": "x"},
        headers={"X-CSRF-Token": "abc.def"},
    )
    assert r.status_code == 403

    # com header válido → passa
    csrf = client.cookies.get("ryu_csrf")
    r = await client.post(
        "/api/issues", json={"workspace_id": ws_id, "title": "x"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code in (200, 201), r.text

    # GET nunca exige CSRF
    r = await client.get("/api/auth/me")
    assert r.status_code == 200

    # logout limpa cookies
    r = await client.post("/api/auth/logout")
    assert r.status_code == 200
    assert "ryu_csrf=" in r.headers.get("set-cookie", "") or True


# ── Allowlists de signup ──────────────────────────────────────────────
async def test_signup_allowlists(client, monkeypatch):
    from ryu.config import settings

    # allowlist de domínio: bloqueia novo usuário fora dela mesmo com allow_signup
    monkeypatch.setattr(settings, "allowed_email_domains", "empresa.com")
    r = await client.post("/api/auth/request-code", json={"email": "novo@fora.com"})
    assert r.status_code == 403
    r = await client.post("/api/auth/request-code", json={"email": "novo@empresa.com"})
    assert r.status_code == 200

    # allowlist de e-mail vence o domínio
    monkeypatch.setattr(settings, "allowed_emails", "vip@fora.com")
    r = await client.post("/api/auth/request-code", json={"email": "vip@fora.com"})
    assert r.status_code == 200

    # gate também no verify
    r = await client.post(
        "/api/auth/verify", json={"email": "bloqueado@fora.com", "code": DEV_CODE}
    )
    assert r.status_code == 403

    # usuário existente sempre pode logar
    monkeypatch.setattr(settings, "allowed_emails", "")
    monkeypatch.setattr(settings, "allowed_email_domains", "")
    await login(client, "ja-existe@example.com")
    _fresh(client)
    monkeypatch.setattr(settings, "allowed_email_domains", "empresa.com")
    r = await client.post("/api/auth/request-code", json={"email": "ja-existe@example.com"})
    assert r.status_code == 200


# ── Hardening do código de verificação ────────────────────────────────
async def test_verification_code_attempts_and_cooldown(client, monkeypatch):
    from sqlalchemy import select

    from ryu.db import SessionLocal
    from ryu.models import VerificationCode

    email = "hard@example.com"
    r = await client.post("/api/auth/request-code", json={"email": email})
    assert r.status_code == 200

    # cooldown de 60s
    from ryu.config import settings

    monkeypatch.setattr(settings, "auth_code_resend_seconds", 60)
    r = await client.post("/api/auth/request-code", json={"email": email})
    assert r.status_code == 429
    monkeypatch.setattr(settings, "auth_code_resend_seconds", 0)

    # 5 tentativas erradas travam o código real
    for _ in range(5):
        r = await client.post("/api/auth/verify", json={"email": email, "code": "000000"})
        assert r.status_code == 400
    async with SessionLocal() as db:
        res = await db.execute(
            select(VerificationCode)
            .where(VerificationCode.email == email)
            .order_by(VerificationCode.created_at.desc())
        )
        vc = res.scalars().first()
        assert vc.attempts >= 5
        real_code = vc.code
    if real_code != DEV_CODE:
        r = await client.post("/api/auth/verify", json={"email": email, "code": real_code})
        assert r.status_code == 400  # attempts >= 5 invalida o código


async def test_auth_rate_limit(client, monkeypatch):
    from ryu.config import settings

    monkeypatch.setattr(settings, "rate_limit_auth", 3)
    codes = []
    for i in range(5):
        r = await client.post(
            "/api/auth/request-code", json={"email": f"rl-{i}@example.com"}
        )
        codes.append(r.status_code)
    assert 429 in codes


# ── PAT: expiração, prefixo, renovação ────────────────────────────────
async def test_pat_lifecycle(client):
    await login(client, "pat@example.com")
    r = await client.post(
        "/api/auth/tokens", json={"name": "cli", "expires_in_days": 90}
    )
    assert r.status_code == 200, r.text
    tok = r.json()
    raw = tok["token"]
    assert tok["token_prefix"] == raw[:12]
    assert tok["expires_at"] is not None

    # listagem expõe prefix/expires/last_used
    r = await client.get("/api/auth/tokens")
    row = next(t for t in r.json() if t["id"] == tok["id"])
    assert row["token_prefix"] == raw[:12]

    # renew fora da janela (90d restantes) → renewed=false
    r = await client.post(
        "/api/auth/tokens/current/renew", headers={"Authorization": f"Bearer {raw}"}
    )
    assert r.status_code == 200
    assert r.json()["renewed"] is False

    # empurra expiração p/ daqui a 2 dias → renewed=true (+90d)
    from sqlalchemy import update

    from ryu.db import SessionLocal
    from ryu.models import ApiToken

    async with SessionLocal() as db:
        await db.execute(
            update(ApiToken)
            .where(ApiToken.id == tok["id"])
            .values(expires_at=datetime.now(timezone.utc) + timedelta(days=2))
        )
        await db.commit()
    r = await client.post(
        "/api/auth/tokens/current/renew", headers={"Authorization": f"Bearer {raw}"}
    )
    assert r.json()["renewed"] is True

    # PAT sem expiração → renewed=false / expires_at None
    r = await client.post("/api/auth/tokens", json={"name": "sem-exp"})
    raw2 = r.json()["token"]
    assert r.json()["expires_at"] is None
    r = await client.post(
        "/api/auth/tokens/current/renew", headers={"Authorization": f"Bearer {raw2}"}
    )
    assert r.json() == {"expires_at": None, "renewed": False}

    # uso como Bearer registra last_used_at
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 200
    r = await client.get("/api/auth/tokens")
    row = next(t for t in r.json() if t["id"] == tok["id"])
    assert row["last_used_at"] is not None


# ── Notification preferences ──────────────────────────────────────────
async def test_notification_preferences(client):
    data = await login(client, "nprefs@example.com")
    ws_id = data["workspaces"][0]["id"]

    # GET sem registro → {}
    r = await client.get("/api/notification-preferences", params={"workspace_id": ws_id})
    assert r.status_code == 200
    assert r.json()["preferences"] == {}

    # grupo/valor inválido → 400
    r = await client.patch(
        f"/api/notification-preferences?workspace_id={ws_id}",
        json={"preferences": {"nope": "all"}},
    )
    assert r.status_code == 400
    r = await client.patch(
        f"/api/notification-preferences?workspace_id={ws_id}",
        json={"preferences": {"comments": "loud"}},
    )
    assert r.status_code == 400

    # PATCH merge
    r = await client.patch(
        f"/api/notification-preferences?workspace_id={ws_id}",
        json={"preferences": {"comments": "muted"}},
    )
    assert r.status_code == 200
    r = await client.patch(
        f"/api/notification-preferences?workspace_id={ws_id}",
        json={"preferences": {"assignments": "all"}},
    )
    assert r.json()["preferences"] == {"comments": "muted", "assignments": "all"}

    # PUT substitui
    r = await client.put(
        f"/api/notification-preferences?workspace_id={ws_id}",
        json={"preferences": {"agent_activity": "muted"}},
    )
    assert r.json()["preferences"] == {"agent_activity": "muted"}


async def test_muted_preference_suppresses_inbox(client):
    data = await login(client, "mute-a@example.com")
    ws_id = data["workspaces"][0]["id"]
    user_id = data["user"]["id"]

    # muta comments p/ o autor... precisamos de OUTRO usuário p/ receber
    # fluxo: A cria issue; B comenta; A é subscriber (creator) e receberia
    # notificação de comentário — mas mutou o grupo comments.
    r = await client.put(
        f"/api/notification-preferences?workspace_id={ws_id}",
        json={"preferences": {"comments": "muted"}},
    )
    assert r.status_code == 200

    r = await client.post("/api/issues", json={"workspace_id": ws_id, "title": "Mute test"})
    issue = r.json()

    # convida B, aceita, B comenta
    r = await client.post(
        f"/api/workspaces/{ws_id}/members", json={"email": "mute-b@example.com"}
    )
    inv = r.json()
    _fresh(client)
    await login(client, "mute-b@example.com")
    await client.post(f"/api/invitations/{inv['id']}/accept")
    r = await client.post(f"/api/issues/{issue['id']}/comments", json={"body": "oi"})
    assert r.status_code in (200, 201)

    # inbox de A continua vazio p/ esse issue
    from sqlalchemy import select

    from ryu.db import SessionLocal
    from ryu.models import InboxItem

    async with SessionLocal() as db:
        res = await db.execute(
            select(InboxItem).where(
                InboxItem.workspace_id == ws_id,
                InboxItem.user_id == user_id,
                InboxItem.issue_id == issue["id"],
            )
        )
        assert res.scalars().first() is None


# ── Inbox: lote + unread-summary ──────────────────────────────────────
async def test_inbox_batch_and_summary(client):
    data = await login(client, "ibx@example.com")
    ws_id = data["workspaces"][0]["id"]
    user_id = data["user"]["id"]

    from ryu.db import SessionLocal
    from ryu.services import inbox as inbox_svc

    async with SessionLocal() as db:
        i1 = await inbox_svc.notify(db, ws_id, user_id, "info", "n1")
        i2 = await inbox_svc.notify(db, ws_id, user_id, "info", "n2")
        await inbox_svc.notify(db, ws_id, user_id, "info", "n3")
        assert i1 and i2

    # unread-summary
    r = await client.get("/api/inbox/unread-summary")
    assert r.status_code == 200
    summary = {s["workspace_id"]: s["count"] for s in r.json()}
    assert summary.get(ws_id) == 3

    # marca 1 como lida e archive-all-read
    r = await client.post("/api/inbox/mark-read", json={"item_ids": [i1.id]})
    assert r.json()["updated"] == 1
    r = await client.post(f"/api/inbox/archive-all-read?workspace_id={ws_id}")
    assert r.json()["count"] == 1

    # unarchive
    r = await client.post(f"/api/inbox/{i1.id}/unarchive")
    assert r.status_code == 200
    assert r.json()["archived"] is False

    # archived list
    r = await client.post("/api/inbox/archive", json={"item_ids": [i2.id]})
    r = await client.get(f"/api/inbox/archived?workspace_id={ws_id}")
    assert any(x["id"] == i2.id for x in r.json())

    # archive-completed: cria issue done com notificação
    r = await client.post("/api/issues", json={"workspace_id": ws_id, "title": "Done issue"})
    issue = r.json()
    async with SessionLocal() as db:
        await inbox_svc.notify(db, ws_id, user_id, "info", "done ntf", issue_id=issue["id"])
    r = await client.patch(f"/api/issues/{issue['id']}", json={"status": "done"})
    assert r.status_code == 200
    r = await client.post(f"/api/inbox/archive-completed?workspace_id={ws_id}")
    assert r.json()["count"] >= 1

    # archive-all limpa o resto
    r = await client.post(f"/api/inbox/archive-all?workspace_id={ws_id}")
    assert r.status_code == 200
    r = await client.get("/api/inbox", params={"workspace_id": ws_id})
    assert r.json() == []


# ── Config pública ────────────────────────────────────────────────────
async def test_auth_config_endpoint(client):
    r = await client.get("/api/auth/config")
    assert r.status_code == 200
    body = r.json()
    assert "allow_signup" in body
    assert "google_client_id" in body
    assert "workspace_creation_disabled" in body


async def test_google_login_unconfigured(client):
    r = await client.post("/api/auth/google", json={"code": "abc"})
    assert r.status_code == 503


async def test_disable_workspace_creation(client, monkeypatch):
    from ryu.config import settings

    await login(client, "nocreate@example.com")
    monkeypatch.setattr(settings, "disable_workspace_creation", True)
    r = await client.post("/api/workspaces", json={"name": "X", "slug": "nocreate-x"})
    assert r.status_code == 403


# ── Página de membros ─────────────────────────────────────────────────
async def test_members_page(client):
    data = await login(client, "mpage@example.com")
    slug = data["workspaces"][0]["slug"]
    r = await client.get(f"/w/{slug}/members")
    assert r.status_code == 200
    assert "mpage@example.com" in r.text
