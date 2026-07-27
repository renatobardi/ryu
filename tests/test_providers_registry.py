"""Registro único de Providers (issue #55).

Os Providers suportados são exatamente claude, devin, agy e opencode; o
registro é a única fonte de verdade (binário, env-key, descrição, instalação
por plataforma, ACP e update). Um agente configurado com Provider removido
falha com razão própria — distinta de "CLI não instalado neste Device" — e o
RuntimeProfile não existe mais.
"""
from __future__ import annotations

from tests.conftest import login

EXPECTED = {"claude", "devin", "agy", "opencode"}


# ── Fonte de verdade única ────────────────────────────────────────────
def test_registry_is_the_single_source_of_providers():
    from ryu import providers
    from ryu.runner import adapters

    assert set(providers.PROVIDERS) == EXPECTED

    for name, spec in providers.PROVIDERS.items():
        assert spec.binary, name
        assert spec.env_key, name
        assert spec.description, name
        assert spec.install["darwin"] and spec.install["win32"], name
        assert isinstance(spec.acp, bool), name

    # o daemon detecta exatamente os Providers do registro
    assert {d["provider"] for d in adapters.detect_runtimes()} == EXPECTED
    # agy é o único sem ACP (ADR-0002)
    assert {n for n, s in providers.PROVIDERS.items() if not s.acp} == {"agy"}


def test_removed_providers_are_not_supported_nor_aliased():
    from ryu import providers

    for gone in ("gemini", "codex", "copilot", "cursor-agent", "qwen"):
        assert not providers.is_supported(gone)
        assert providers.get(gone) is None


# ── Resolução: não suportado ≠ não instalado ──────────────────────────
def test_resolution_failure_distinguishes_unsupported_from_missing(monkeypatch, tmp_path):
    from ryu.runner import adapters

    reason, message = adapters.resolution_failure("gemini")
    assert reason == "provider_unsupported"
    assert "gemini" in message

    monkeypatch.setenv("RYU_AGY_PATH", str(tmp_path / "nao-existe"))
    reason, message = adapters.resolution_failure("agy")
    assert reason == "runtime_missing"
    assert "agy" in message
    assert "instalado" in message

    # devin é ACP-only (ADR-0002): instalado, mas o Daemon ainda não fala ACP
    fake = tmp_path / "devin"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("RYU_DEVIN_PATH", str(fake))
    reason, message = adapters.resolution_failure("devin")
    assert reason == "runtime_missing"
    assert "ACP" in message


# ── Servidor: task de agente com Provider removido falha ──────────────
async def test_sweeper_fails_queued_task_of_unsupported_provider(client):
    from ryu.db import SessionLocal
    from ryu.models import Agent, AgentTask
    from ryu.runner.loop import _sweep

    data = await login(client, "providers-unsupported@example.com")
    ws_id = data["workspaces"][0]["id"]

    # agente legado apontando para um Provider que saiu do suporte
    async with SessionLocal() as db:
        agent = Agent(workspace_id=ws_id, name="Legado", handle="legado", runtime="gemini")
        db.add(agent)
        await db.commit()
        task = AgentTask(
            workspace_id=ws_id, agent_id=agent.id, kind="issue", status="queued", prompt="oi"
        )
        db.add(task)
        await db.commit()
        task_id = task.id

    await _sweep()

    r = await client.get(f"/api/tasks/{task_id}")
    body = r.json()
    assert body["status"] == "failed"
    assert body["failure_reason"] == "provider_unsupported"


async def test_explicit_command_bypasses_the_registry(client):
    """runtime_config.command monta o argv sem consultar o registro (docs/PARITY.md)
    — falhar essas tasks por Provider seria falso."""
    from ryu.db import SessionLocal
    from ryu.models import Agent, AgentTask
    from ryu.runner.loop import _sweep

    data = await login(client, "providers-bypass@example.com")
    ws_id = data["workspaces"][0]["id"]

    async with SessionLocal() as db:
        agent = Agent(
            workspace_id=ws_id, name="Eco", handle="eco", runtime="echo-fallback",
            runtime_config={"command": ["echo", "{prompt}"]},
        )
        db.add(agent)
        await db.commit()
        task = AgentTask(
            workspace_id=ws_id, agent_id=agent.id, kind="issue", status="queued", prompt="oi"
        )
        db.add(task)
        await db.commit()
        task_id = task.id

    await _sweep()

    r = await client.get(f"/api/tasks/{task_id}")
    assert r.json()["status"] == "queued"


async def test_supported_provider_task_stays_queued(client):
    from ryu.db import SessionLocal
    from ryu.models import AgentTask
    from ryu.runner.loop import _sweep

    data = await login(client, "providers-supported@example.com")
    ws_id = data["workspaces"][0]["id"]
    r = await client.post(
        "/api/agents",
        json={"workspace_id": ws_id, "name": "Claudio", "handle": "claudio", "runtime": "claude"},
    )
    assert r.status_code == 201, r.text
    agent = r.json()

    async with SessionLocal() as db:
        task = AgentTask(
            workspace_id=ws_id, agent_id=agent["id"], kind="issue", status="queued", prompt="oi"
        )
        db.add(task)
        await db.commit()
        task_id = task.id

    await _sweep()

    r = await client.get(f"/api/tasks/{task_id}")
    assert r.json()["status"] == "queued"


# ── RuntimeProfile removido ───────────────────────────────────────────
async def test_runtime_profile_endpoints_are_gone(client):
    data = await login(client, "providers-profile@example.com")
    ws_id = data["workspaces"][0]["id"]

    r = await client.get("/api/runtime-profiles", params={"workspace_id": ws_id})
    assert r.status_code == 404
    r = await client.post(
        "/api/runtime-profiles",
        json={"workspace_id": ws_id, "display_name": "x", "command_name": "x"},
    )
    assert r.status_code == 404

    r = await client.post(
        "/api/agents",
        json={"workspace_id": ws_id, "name": "Sem perfil", "handle": "semperfil", "runtime": "claude"},
    )
    assert r.status_code == 201, r.text
    assert "profile_id" not in r.json()
