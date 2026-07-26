"""Fixtures de teste do Ryu.

IMPORTANTE: as env vars RYU_* são setadas AQUI, no import do conftest,
antes de qualquer `import ryu.*` — ryu.config instancia Settings no import.
DB sqlite em diretório temporário; código de verificação dev fixo.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

DEV_CODE = "424242"

_TMP = Path(tempfile.mkdtemp(prefix="ryu-test-"))
os.environ["RYU_DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP}/ryu.db"
os.environ["RYU_DEV_VERIFICATION_CODE"] = DEV_CODE
os.environ["RYU_DATA_DIR"] = str(_TMP)
os.environ["RYU_WORKSPACES_ROOT"] = str(_TMP / "workspaces")
os.environ["RYU_UPLOADS_DIR"] = str(_TMP / "uploads")
os.environ["RYU_JWT_SECRET"] = "test-secret-0123456789abcdef0123456789abcdef"
# workspace-auth ciclo 1: sem cooldown/rate-limit nos testes (logins repetidos)
os.environ["RYU_AUTH_CODE_RESEND_SECONDS"] = "0"
os.environ["RYU_RATE_LIMIT_AUTH"] = "0"
os.environ["RYU_RATE_LIMIT_AUTH_VERIFY"] = "0"

import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402


@pytest_asyncio.fixture
async def client():
    """AsyncClient sobre o app via ASGITransport (lifespan NÃO roda; init_db manual).

    O engine é descartado no teardown para não vazar conexões aiosqlite
    entre event loops de testes diferentes (loop por função).
    """
    from ryu.db import engine, init_db
    from ryu.main import app

    await init_db()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await engine.dispose()


async def login(client: httpx.AsyncClient, email: str) -> dict:
    """Login por código dev; retorna payload do verify (user + workspaces)."""
    r = await client.post("/api/auth/request-code", json={"email": email})
    assert r.status_code == 200, r.text
    r = await client.post("/api/auth/verify", json={"email": email, "code": DEV_CODE})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["workspaces"], "workspace pessoal deveria ser criado no 1º login"
    # auth via cookie exige X-CSRF-Token em métodos mutantes (workspace-auth ciclo 1)
    csrf = client.cookies.get("ryu_csrf")
    if csrf:
        client.headers["X-CSRF-Token"] = csrf
    return data
