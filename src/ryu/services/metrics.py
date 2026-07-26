"""Métricas Prometheus do Ryu — geradas manualmente, SEM dependência nova.

Formato de texto plano compatível com o Prometheus exposition format
(https://prometheus.io/docs/instrumenting/exposition_formats/), montado à
mão com contadores/histogramas simples em memória (dict). Nenhuma lib
externa (prometheus_client) é usada — paridade funcional com o objetivo do
gap, mas sem novo pacote no pyproject.

Cobertura:
- HTTP: requests_total / request_duration_seconds (sum+count) / in_flight
  por método+rota+status, coletado pelo middleware em main.py.
- Negócio (runner): tasks terminais por status, falhas por razão, tokens e
  custo LLM por provider/model (chamado por services.agents.record_task_usage
  e runner/loop.py).
- build_info + gauges amostrados on-demand do DB (fila por status, agentes
  por status, runtimes online) — calculados na hora do GET /metrics.

Ativação: settings.metrics_enabled (env RYU_METRICS_ENABLED, default true).
Quando desligado, GET /metrics responde 404 (paridade "opcional por env").
"""
from __future__ import annotations

import threading
from collections import defaultdict

_lock = threading.Lock()

# ── HTTP ────────────────────────────────────────────────────────────────
_http_requests: dict[tuple[str, str, str], int] = defaultdict(int)
_http_duration_sum: dict[tuple[str, str], float] = defaultdict(float)
_http_duration_count: dict[tuple[str, str], int] = defaultdict(int)
_http_in_flight: int = 0

# ── Negócio ───────────────────────────────────────────────────────────
_tasks_enqueued: dict[str, int] = defaultdict(int)
_tasks_dispatched: int = 0
_tasks_started: int = 0
_tasks_terminal: dict[str, int] = defaultdict(int)
_tasks_failed: dict[str, int] = defaultdict(int)
_queue_wait_sum: float = 0.0
_queue_wait_count: int = 0
_run_seconds_sum: float = 0.0
_run_seconds_count: int = 0

_llm_tokens: dict[tuple[str, str, str], int] = defaultdict(int)
_llm_cost_usd: dict[tuple[str, str, str], float] = defaultdict(float)
_llm_unpriced_tokens: dict[tuple[str, str], int] = defaultdict(int)


def _esc(v: str) -> str:
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def observe_http(method: str, route: str, status: int, duration_seconds: float) -> None:
    with _lock:
        _http_requests[(method, route, str(status))] += 1
        _http_duration_sum[(method, route)] += max(0.0, duration_seconds)
        _http_duration_count[(method, route)] += 1


def http_in_flight_inc() -> None:
    global _http_in_flight
    with _lock:
        _http_in_flight += 1


def http_in_flight_dec() -> None:
    global _http_in_flight
    with _lock:
        _http_in_flight = max(0, _http_in_flight - 1)


def task_enqueued(kind: str = "issue") -> None:
    with _lock:
        _tasks_enqueued[kind or "issue"] += 1


def task_dispatched() -> None:
    global _tasks_dispatched
    with _lock:
        _tasks_dispatched += 1


def task_started(queue_wait_seconds: float | None = None) -> None:
    global _tasks_started, _queue_wait_sum, _queue_wait_count
    with _lock:
        _tasks_started += 1
        if queue_wait_seconds is not None and queue_wait_seconds >= 0:
            _queue_wait_sum += queue_wait_seconds
            _queue_wait_count += 1


def task_terminal(status: str, *, reason: str | None = None, run_seconds: float | None = None) -> None:
    global _run_seconds_sum, _run_seconds_count
    with _lock:
        _tasks_terminal[status] += 1
        if status == "failed":
            _tasks_failed[reason or "unknown"] += 1
        if run_seconds is not None and run_seconds >= 0:
            _run_seconds_sum += run_seconds
            _run_seconds_count += 1


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
    with _lock:
        for kind, tokens in (
            ("input", input_tokens),
            ("output", output_tokens),
            ("cache_read", cache_read_tokens),
            ("cache_write", cache_write_tokens),
        ):
            if tokens:
                _llm_tokens[(p, m, kind)] += int(tokens)
        if cost_usd:
            _llm_cost_usd[(p, m, cost_source)] += float(cost_usd)
        if unpriced:
            total = (input_tokens or 0) + (output_tokens or 0) + (cache_read_tokens or 0) + (cache_write_tokens or 0)
            if total:
                _llm_unpriced_tokens[(p, m)] += int(total)


async def _sample_db_gauges() -> list[str]:
    """Amostra on-demand (no request do /metrics) dos gauges derivados do DB."""
    from sqlalchemy import func, select

    from ryu.db import SessionLocal
    from ryu.models import Agent, AgentRuntime, AgentTask

    lines: list[str] = []
    async with SessionLocal() as db:
        rows = (await db.execute(select(AgentTask.status, func.count()).group_by(AgentTask.status))).all()
        counts = {s: int(c) for s, c in rows}
        lines.append("# HELP ryu_agent_task_queue_depth Tasks por status (amostrado)")
        lines.append("# TYPE ryu_agent_task_queue_depth gauge")
        for status in ("queued", "dispatched", "running", "completed", "failed", "cancelled"):
            lines.append(f'ryu_agent_task_queue_depth{{status="{status}"}} {counts.get(status, 0)}')

        rows = (await db.execute(select(Agent.status, func.count()).group_by(Agent.status))).all()
        seen = {s: int(c) for s, c in rows}
        lines.append("# HELP ryu_agents_by_status Agentes por status (amostrado)")
        lines.append("# TYPE ryu_agents_by_status gauge")
        for status in ("idle", "working", "blocked", "error", "offline"):
            lines.append(f'ryu_agents_by_status{{status="{status}"}} {seen.get(status, 0)}')

        online = (
            await db.execute(select(func.count()).select_from(AgentRuntime).where(AgentRuntime.status == "online"))
        ).scalar_one()
        lines.append("# HELP ryu_agent_runtimes_online Runtimes externos online (amostrado)")
        lines.append("# TYPE ryu_agent_runtimes_online gauge")
        lines.append(f"ryu_agent_runtimes_online {int(online)}")
    return lines


async def render(*, version: str = "0.1.0", app_name: str = "ryu", sample_db: bool = True) -> str:
    """Monta o corpo texto-plano do /metrics (paridade prometheus exposition format)."""
    lines: list[str] = []
    lines.append("# HELP ryu_build_info Build info")
    lines.append("# TYPE ryu_build_info gauge")
    lines.append(f'ryu_build_info{{version="{_esc(version)}",app="{_esc(app_name)}"}} 1')

    with _lock:
        lines.append("# HELP ryu_http_requests_total Total de requests HTTP")
        lines.append("# TYPE ryu_http_requests_total counter")
        for (method, route, status), n in sorted(_http_requests.items()):
            lines.append(
                f'ryu_http_requests_total{{method="{_esc(method)}",route="{_esc(route)}",status="{status}"}} {n}'
            )

        lines.append("# HELP ryu_http_request_duration_seconds Duração dos requests HTTP")
        lines.append("# TYPE ryu_http_request_duration_seconds summary")
        for (method, route), s in sorted(_http_duration_sum.items()):
            c = _http_duration_count[(method, route)]
            lines.append(f'ryu_http_request_duration_seconds_sum{{method="{_esc(method)}",route="{_esc(route)}"}} {s}')
            lines.append(f'ryu_http_request_duration_seconds_count{{method="{_esc(method)}",route="{_esc(route)}"}} {c}')

        lines.append("# HELP ryu_http_requests_in_flight Requests HTTP em andamento")
        lines.append("# TYPE ryu_http_requests_in_flight gauge")
        lines.append(f"ryu_http_requests_in_flight {_http_in_flight}")

        lines.append("# HELP ryu_agent_tasks_enqueued_total Tasks enfileiradas")
        lines.append("# TYPE ryu_agent_tasks_enqueued_total counter")
        for kind, n in sorted(_tasks_enqueued.items()):
            lines.append(f'ryu_agent_tasks_enqueued_total{{kind="{_esc(kind)}"}} {n}')

        lines.append("# HELP ryu_agent_tasks_dispatched_total Tasks despachadas (claim)")
        lines.append("# TYPE ryu_agent_tasks_dispatched_total counter")
        lines.append(f"ryu_agent_tasks_dispatched_total {_tasks_dispatched}")

        lines.append("# HELP ryu_agent_tasks_started_total Tasks iniciadas (running)")
        lines.append("# TYPE ryu_agent_tasks_started_total counter")
        lines.append(f"ryu_agent_tasks_started_total {_tasks_started}")

        lines.append("# HELP ryu_agent_tasks_terminal_total Tasks terminais")
        lines.append("# TYPE ryu_agent_tasks_terminal_total counter")
        for status, n in sorted(_tasks_terminal.items()):
            lines.append(f'ryu_agent_tasks_terminal_total{{status="{_esc(status)}"}} {n}')

        lines.append("# HELP ryu_agent_tasks_failed_total Tasks falhas por razão")
        lines.append("# TYPE ryu_agent_tasks_failed_total counter")
        for reason, n in sorted(_tasks_failed.items()):
            lines.append(f'ryu_agent_tasks_failed_total{{reason="{_esc(reason)}"}} {n}')

        lines.append("# HELP ryu_agent_task_queue_wait_seconds Tempo entre enqueue e início da execução")
        lines.append("# TYPE ryu_agent_task_queue_wait_seconds summary")
        lines.append(f"ryu_agent_task_queue_wait_seconds_sum {_queue_wait_sum}")
        lines.append(f"ryu_agent_task_queue_wait_seconds_count {_queue_wait_count}")

        lines.append("# HELP ryu_agent_task_run_seconds Duração de execução de tasks terminais")
        lines.append("# TYPE ryu_agent_task_run_seconds summary")
        lines.append(f"ryu_agent_task_run_seconds_sum {_run_seconds_sum}")
        lines.append(f"ryu_agent_task_run_seconds_count {_run_seconds_count}")

        lines.append("# HELP ryu_llm_tokens_total Tokens LLM consumidos")
        lines.append("# TYPE ryu_llm_tokens_total counter")
        for (p, m, kind), n in sorted(_llm_tokens.items()):
            lines.append(f'ryu_llm_tokens_total{{provider="{_esc(p)}",model="{_esc(m)}",kind="{kind}"}} {n}')

        lines.append("# HELP ryu_llm_cost_usd_total Custo LLM (autoritativo + estimado)")
        lines.append("# TYPE ryu_llm_cost_usd_total counter")
        for (p, m, source), v in sorted(_llm_cost_usd.items()):
            lines.append(f'ryu_llm_cost_usd_total{{provider="{_esc(p)}",model="{_esc(m)}",source="{source}"}} {v}')

        lines.append("# HELP ryu_llm_unpriced_tokens_total Tokens sem preço mapeado")
        lines.append("# TYPE ryu_llm_unpriced_tokens_total counter")
        for (p, m), n in sorted(_llm_unpriced_tokens.items()):
            lines.append(f'ryu_llm_unpriced_tokens_total{{provider="{_esc(p)}",model="{_esc(m)}"}} {n}')

    if sample_db:
        try:
            lines.extend(await _sample_db_gauges())
        except Exception:
            pass

    return "\n".join(lines) + "\n"


def _reset_for_tests() -> None:
    """Só para testes — zera os contadores in-memory entre casos."""
    global _http_in_flight, _tasks_dispatched, _tasks_started
    global _queue_wait_sum, _queue_wait_count, _run_seconds_sum, _run_seconds_count
    with _lock:
        _http_requests.clear()
        _http_duration_sum.clear()
        _http_duration_count.clear()
        _http_in_flight = 0
        _tasks_enqueued.clear()
        _tasks_dispatched = 0
        _tasks_started = 0
        _tasks_terminal.clear()
        _tasks_failed.clear()
        _queue_wait_sum = 0.0
        _queue_wait_count = 0
        _run_seconds_sum = 0.0
        _run_seconds_count = 0
        _llm_tokens.clear()
        _llm_cost_usd.clear()
        _llm_unpriced_tokens.clear()
