"""Testes do domínio usage-observability: pricing, rollup incremental,
dashboards, /metrics, feature flags e /readyz."""
from __future__ import annotations

from tests.conftest import login


async def _mk_agent(client, ws_id: str, name: str, **extra) -> dict:
    r = await client.post(
        "/api/agents",
        json={"workspace_id": ws_id, "name": name, "handle": name.lower(), "runtime": "echo-fallback", **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _mk_issue_with_task(client, ws_id: str, agent_id: str, title: str) -> tuple[dict, dict]:
    r = await client.post(
        "/api/issues",
        json={
            "workspace_id": ws_id, "title": title, "status": "todo",
            "assignee_type": "agent", "assignee_id": agent_id,
        },
    )
    assert r.status_code == 201, r.text
    issue = r.json()
    r = await client.get("/api/tasks", params={"workspace_id": ws_id, "issue_id": issue["id"]})
    tasks = r.json()
    return issue, tasks[0]


# ── Pricing ─────────────────────────────────────────────────────────────
def test_pricing_estimate_and_authoritative():
    from ryu.services.pricing import estimate_cost_usd, price_for_model_alias

    price = price_for_model_alias("claude-sonnet-5")
    assert price is not None
    est = estimate_cost_usd("anthropic", "claude-sonnet-5", 1_000_000, 1_000_000)
    assert est is not None and est > 0

    # modelo totalmente desconhecido -> None (uncosted), nunca custo chutado
    assert estimate_cost_usd("acme", "modelo-inexistente-xyz", 100, 100) is None


async def test_record_task_usage_estimates_cost_when_not_reported(client):
    data = await login(client, "usage-obs-cost@example.com")
    ws_id = data["workspaces"][0]["id"]
    agent = await _mk_agent(client, ws_id, "Cost")
    issue, task = await _mk_issue_with_task(client, ws_id, agent["id"], "cost")

    # sem cost_usd no payload -> deve estimar via pricing table
    r = await client.post(
        f"/api/tasks/{task['id']}/usage",
        json={"provider": "anthropic", "model": "claude-sonnet-5", "input_tokens": 1000, "output_tokens": 500},
    )
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["cost_usd"] > 0
    assert row["runtime"] == "echo-fallback"


# ── Rollup incremental ──────────────────────────────────────────────────
async def test_usage_rollup_incremental(client):
    data = await login(client, "usage-obs-rollup@example.com")
    ws_id = data["workspaces"][0]["id"]
    agent = await _mk_agent(client, ws_id, "Rollup")
    issue, task = await _mk_issue_with_task(client, ws_id, agent["id"], "rollup")

    r = await client.post(
        f"/api/tasks/{task['id']}/usage",
        json={"provider": "anthropic", "model": "claude-sonnet-5", "input_tokens": 2000, "output_tokens": 1000,
              "cost_usd": 0.05},
    )
    assert r.status_code == 201, r.text

    from ryu.db import SessionLocal
    from ryu.services.rollup import run_rollup
    from ryu.models import UsageRollupDaily, UsageRollupHourly
    from sqlalchemy import select

    async with SessionLocal() as db:
        result = await run_rollup(db)
        assert result["rows_processed"] >= 1

        daily = (
            await db.execute(select(UsageRollupDaily).where(UsageRollupDaily.workspace_id == ws_id))
        ).scalars().all()
        assert len(daily) >= 1
        assert daily[0].input_tokens == 2000
        assert daily[0].cost_usd_costed > 0

        hourly = (
            await db.execute(select(UsageRollupHourly).where(UsageRollupHourly.workspace_id == ws_id))
        ).scalars().all()
        assert len(hourly) >= 1

        # re-executar sem novas linhas -> idempotente (0 processadas)
        result2 = await run_rollup(db)
        assert result2["rows_processed"] == 0
        daily2 = (
            await db.execute(select(UsageRollupDaily).where(UsageRollupDaily.workspace_id == ws_id))
        ).scalars().all()
        assert daily2[0].input_tokens == 2000  # não duplicou


# ── Dashboards ────────────────────────────────────────────────────────
async def test_dashboard_usage_and_runtime_endpoints(client):
    data = await login(client, "usage-obs-dash@example.com")
    ws_id = data["workspaces"][0]["id"]
    agent = await _mk_agent(client, ws_id, "Dash")
    issue, task = await _mk_issue_with_task(client, ws_id, agent["id"], "dash")
    await client.post(
        f"/api/tasks/{task['id']}/usage",
        json={"provider": "anthropic", "model": "claude-sonnet-5", "input_tokens": 100, "output_tokens": 50,
              "cost_usd": 0.001},
    )

    r = await client.get("/api/dashboard/usage/daily", params={"workspace_id": ws_id})
    assert r.status_code == 200, r.text
    assert r.json()["by_day"]

    r = await client.get("/api/dashboard/usage/by-agent", params={"workspace_id": ws_id})
    assert r.status_code == 200
    body = r.json()
    assert any(a["agent_id"] == agent["id"] for a in body["by_agent"])

    r = await client.get("/api/dashboard/usage/by-hour", params={"workspace_id": ws_id})
    assert r.status_code == 200
    assert len(r.json()["by_hour"]) == 24

    r = await client.get("/api/dashboard/agent-runtime", params={"workspace_id": ws_id})
    assert r.status_code == 200

    r = await client.get("/api/dashboard/runtime/daily", params={"workspace_id": ws_id})
    assert r.status_code == 200

    r = await client.get("/api/dashboard/runtimes/echo-fallback/usage", params={"workspace_id": ws_id})
    assert r.status_code == 200

    r = await client.get("/api/dashboard/agent-activity-30d", params={"workspace_id": ws_id})
    assert r.status_code == 200

    r = await client.get("/api/dashboard/agent-run-counts", params={"workspace_id": ws_id})
    assert r.status_code == 200
    counts = r.json()["counts"]
    assert any(c["agent_id"] == agent["id"] for c in counts)


# ── /metrics ──────────────────────────────────────────────────────────
async def test_metrics_endpoint_exposes_prometheus_text(client):
    data = await login(client, "usage-obs-metrics@example.com")
    ws_id = data["workspaces"][0]["id"]
    agent = await _mk_agent(client, ws_id, "Metrics")
    await _mk_issue_with_task(client, ws_id, agent["id"], "metrics")

    r = await client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert "ryu_http_requests_total" in body
    assert "ryu_build_info" in body
    assert "ryu_agent_task_queue_depth" in body


async def test_metrics_disabled_returns_404(client, monkeypatch):
    from ryu.config import settings

    settings.metrics_enabled = False
    try:
        r = await client.get("/metrics")
        assert r.status_code == 404
    finally:
        settings.metrics_enabled = True


# ── Feature flags ───────────────────────────────────────────────────────
def test_feature_flags_env_override(monkeypatch):
    from ryu.featureflags import flags

    monkeypatch.setenv("FF_MY_TEST_FLAG", "true")
    assert flags.is_enabled("my_test_flag") is True
    monkeypatch.setenv("FF_MY_TEST_FLAG", "false")
    assert flags.is_enabled("my_test_flag") is False
    monkeypatch.delenv("FF_MY_TEST_FLAG", raising=False)
    assert flags.is_enabled("my_test_flag", default=True) is True


def test_feature_flags_percent_rollout_is_deterministic(monkeypatch):
    from ryu.featureflags import flags

    monkeypatch.setenv("FF_ROLLOUT_TEST", "50%")
    first = flags.is_enabled("rollout_test", subject="user-123")
    second = flags.is_enabled("rollout_test", subject="user-123")
    assert first == second  # mesmo sujeito -> mesmo lado do rollout
    monkeypatch.delenv("FF_ROLLOUT_TEST", raising=False)


async def test_public_config_endpoint_exposes_flags(client):
    r = await client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert "flags" in body and isinstance(body["flags"], dict)


# ── Readiness ─────────────────────────────────────────────────────────
async def test_readyz_ok(client):
    r = await client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


async def test_healthz_still_static(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True
