"""Métricas Prometheus do Ryu (paridade server/internal/metrics do multica).

- HTTP: ryu_http_requests_total / ryu_http_request_duration_seconds /
  ryu_http_requests_in_flight (middleware em main.py, rota templated).
- Negócio (runner): tasks enqueued/dispatched/started/terminal/failed,
  queue_wait_seconds, run_seconds; LLM tokens_total / cost_usd_total /
  unpriced_tokens_total por provider/model.
- build_info (registry.go) + gauges amostrados do DB (business_sampler):
  profundidade da fila por status, agentes por status, runtimes online.

Exposição: listener HTTP separado ativado por RYU_METRICS_ADDR
(equivalente ao METRICS_ADDR do multica; ex.: ":9464" ou "0.0.0.0:9464").
Sem a env var configurada: NO-OP com log claro — as métricas continuam
sendo coletadas em memória, só não são servidas.
"""
from __future__ import annotations

import asyncio
import contextlib

import structlog
from prometheus_client import (
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    start_http_server,
)

log = structlog.get_logger("ryu.metrics")

# ── HTTP (http.go) ────────────────────────────────────────────────────
HTTP_REQUESTS = Counter(
    "ryu_http_requests_total", "Total de requests HTTP", ["method", "route", "status"]
)
HTTP_DURATION = Histogram(
    "ryu_http_request_duration_seconds",
    "Duração dos requests HTTP",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
HTTP_IN_FLIGHT = Gauge("ryu_http_requests_in_flight", "Requests HTTP em andamento")

# ── Negócio (business.go) ─────────────────────────────────────────────
TASKS_ENQUEUED = Counter("ryu_agent_tasks_enqueued_total", "Tasks enfileiradas", ["kind"])
TASKS_DISPATCHED = Counter("ryu_agent_tasks_dispatched_total", "Tasks despachadas (claim)")
TASKS_STARTED = Counter("ryu_agent_tasks_started_total", "Tasks iniciadas (running)")
TASKS_TERMINAL = Counter(
    "ryu_agent_tasks_terminal_total", "Tasks terminais", ["status"]  # completed|failed|cancelled
)
TASKS_FAILED = Counter("ryu_agent_tasks_failed_total", "Tasks falhas por razão", ["reason"])
TASK_QUEUE_WAIT = Histogram(
    "ryu_agent_task_queue_wait_seconds",
    "Tempo entre enqueue e início da execução",
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300, 900, 3600),
)
TASK_RUN_SECONDS = Histogram(
    "ryu_agent_task_run_seconds",
    "Duração de execução de tasks terminais",
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600),
)

LLM_TOKENS = Counter(
    "ryu_llm_tokens_total",
    "Tokens LLM consumidos",
    ["provider", "model", "kind"],  # kind: input|output|cache_read|cache_write
)
LLM_COST_USD = Counter(
    "ryu_llm_cost_usd_total", "Custo LLM (autoritativo + estimado)", ["provider", "model", "source"]
)
LLM_UNPRICED_TOKENS = Counter(
    "ryu_llm_unpriced_tokens_total",
    "Tokens sem preço mapeado (modelo fora da pricing table)",
    ["provider", "model"],
)

# ── build_info (registry.go) ─────────────────────────────────────────
BUILD_INFO = Gauge("ryu_build_info", "Build info", ["version", "app"])

# ── Gauges amostrados do DB (business_sampler*.go / db.go) ────────────
QUEUE_DEPTH = Gauge("ryu_agent_task_queue_depth", "Tasks por status (amostrado)", ["status"])
AGENTS_BY_STATUS = Gauge("ryu_agents_by_status", "Agentes por status (amostrado)", ["status"])
RUNTIMES_ONLINE = Gauge("ryu_agent_runtimes_online", "Runtimes externos online (amostrado)")

_SAMPLE_STATUSES = ("queued", "dispatched", "running", "completed", "failed", "cancelled")

_sampler_task: asyncio.Task | None = None
_server_started = False


def observe_http(method: str, route: str, status: int, duration: float) -> None:
    HTTP_REQUESTS.labels(method=method, route=route, status=str(status)).inc()
    HTTP_DURATION.labels(method=method, route=route).observe(duration)


def task_enqueued(kind: str = "issue") -> None:
    TASKS_ENQUEUED.labels(kind=kind or "issue").inc()


def task_dispatched() -> None:
    TASKS_DISPATCHED.inc()


def task_started(created_at=None, started_at=None) -> None:
    TASKS_STARTED.inc()
    if created_at is not None and started_at is not None:
        with contextlib.suppress(Exception):
            wait = (started_at - created_at).total_seconds()
            if wait >= 0:
                TASK_QUEUE_WAIT.observe(wait)


def task_terminal(status: str, *, reason: str | None = None, run_seconds: float | None = None) -> None:
    TASKS_TERMINAL.labels(status=status).inc()
    if status == "failed":
        TASKS_FAILED.labels(reason=reason or "unknown").inc()
    if run_seconds is not None and run_seconds >= 0:
        TASK_RUN_SECONDS.observe(run_seconds)


def llm_usage(
    provider: str,
    model: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    cost_usd: float = 0.0,
    cost_source: str = "estimated",  # provider|estimated
    unpriced: bool = False,
) -> None:
    p, m = provider or "unknown", model or "unknown"
    for kind, tokens in (
        ("input", input_tokens),
        ("output", output_tokens),
        ("cache_read", cache_read_tokens),
        ("cache_write", cache_write_tokens),
    ):
        if tokens:
            LLM_TOKENS.labels(provider=p, model=m, kind=kind).inc(tokens)
    if cost_usd:
        LLM_COST_USD.labels(provider=p, model=m, source=cost_source).inc(cost_usd)
    if unpriced:
        total = (input_tokens or 0) + (output_tokens or 0) + (cache_read_tokens or 0) + (cache_write_tokens or 0)
        if total:
            LLM_UNPRICED_TOKENS.labels(provider=p, model=m).inc(total)


async def _sample_db_gauges() -> None:
    """Uma rodada de amostragem dos gauges derivados do DB."""
    from sqlalchemy import func, select

    from ryu.db import SessionLocal
    from ryu.models import Agent, AgentRuntime, AgentTask

    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(AgentTask.status, func.count()).group_by(AgentTask.status)
            )
        ).all()
        counts = {s: int(c) for s, c in rows}
        for status in _SAMPLE_STATUSES:
            QUEUE_DEPTH.labels(status=status).set(counts.get(status, 0))
        rows = (
            await db.execute(select(Agent.status, func.count()).group_by(Agent.status))
        ).all()
        seen = {s: int(c) for s, c in rows}
        for status in ("idle", "working", "blocked", "error", "offline"):
            AGENTS_BY_STATUS.labels(status=status).set(seen.get(status, 0))
        online = (
            await db.execute(
                select(func.count()).select_from(AgentRuntime).where(AgentRuntime.status == "online")
            )
        ).scalar_one()
        RUNTIMES_ONLINE.set(int(online))


async def _sampler_loop(interval: float = 15.0) -> None:
    while True:
        try:
            await _sample_db_gauges()
        except Exception:
            log.warning("metrics_sampler_failed")
        await asyncio.sleep(interval)


def start_metrics(version: str = "0.1.0", app_name: str = "ryu") -> None:
    """Sobe o listener /metrics se RYU_METRICS_ADDR estiver configurado.

    Idempotente; NO-OP (com log) quando o addr não está configurado.
    """
    global _sampler_task, _server_started
    from ryu.config import settings

    BUILD_INFO.labels(version=version, app=app_name).set(1)

    addr = getattr(settings, "metrics_addr", None)
    if not addr:
        log.info("metrics_disabled", reason="RYU_METRICS_ADDR não configurado — /metrics inativo")
        return
    host, _, port_s = str(addr).rpartition(":")
    host = host or "0.0.0.0"
    try:
        port = int(port_s)
    except ValueError:
        log.warning("metrics_addr_invalid", addr=addr)
        return
    if not _server_started:
        try:
            start_http_server(port, addr=host, registry=REGISTRY)
            _server_started = True
            log.info("metrics_listener_started", addr=f"{host}:{port}")
        except Exception:
            log.exception("metrics_listener_failed", addr=addr)
            return
    if _sampler_task is None or _sampler_task.done():
        _sampler_task = asyncio.get_event_loop().create_task(_sampler_loop())


async def stop_metrics() -> None:
    global _sampler_task
    if _sampler_task is not None:
        _sampler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _sampler_task
        _sampler_task = None
