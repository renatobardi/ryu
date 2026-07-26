"""Smoke tests: app sobe, healthz, auth por código dev, proteção 401."""
from __future__ import annotations

import importlib
import pkgutil

from fastapi import APIRouter

from tests.conftest import DEV_CODE, login


def test_every_api_module_exposes_router():
    """CONTRACTS.md item 3: todos os routers expõem `router = APIRouter()`."""
    import ryu.api

    missing = []
    for mod in pkgutil.iter_modules(ryu.api.__path__):
        module = importlib.import_module(f"ryu.api.{mod.name}")
        if not isinstance(getattr(module, "router", None), APIRouter):
            missing.append(mod.name)
    assert missing == []


async def test_healthz(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["app"] == "Ryu"


async def test_login_dev_code_creates_user_and_workspace(client):
    data = await login(client, "smoke-user@example.com")
    assert data["user"]["email"] == "smoke-user@example.com"
    ws = data["workspaces"][0]
    assert ws["slug"]
    assert ws["id"]

    # cookie de sessão funciona
    r = await client.get("/api/auth/me")
    assert r.status_code == 200
    me = r.json()
    assert me["email"] == "smoke-user@example.com"
    assert any(w["slug"] == ws["slug"] for w in me["workspaces"])

    # login repetido não duplica workspace
    r = await client.post(
        "/api/auth/verify", json={"email": "smoke-user@example.com", "code": DEV_CODE}
    )
    assert r.status_code == 200
    assert len(r.json()["workspaces"]) == 1


async def test_wrong_code_rejected(client):
    r = await client.post("/api/auth/request-code", json={"email": "smoke-bad@example.com"})
    assert r.status_code == 200
    r = await client.post(
        "/api/auth/verify", json={"email": "smoke-bad@example.com", "code": "000000"}
    )
    assert r.status_code == 400


async def test_requires_auth(client):
    r = await client.get("/api/issues", params={"workspace_id": "nope"})
    assert r.status_code == 401
    r = await client.get("/api/inbox", params={"workspace_id": "nope"})
    assert r.status_code == 401
    r = await client.get("/api/usage/summary", params={"workspace_id": "nope"})
    assert r.status_code == 401


async def test_pat_token_roundtrip(client):
    await login(client, "smoke-pat@example.com")
    r = await client.post("/api/auth/tokens", json={"name": "ci"})
    assert r.status_code == 200
    token = r.json()["token"]
    assert token.startswith("ryu_")

    import httpx
    from ryu.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as anon:
        r = await anon.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["email"] == "smoke-pat@example.com"
