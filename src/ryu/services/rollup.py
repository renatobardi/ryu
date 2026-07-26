"""Rollups incrementais de usage — hourly/daily (paridade multica *_dirty +
*_rollup_state).

Estratégia: em vez de marcar linhas "dirty" e varrer flags, guardamos um
watermark único (UsageRollupState.last_processed_at = MAX(TaskUsage.created_at)
já processado) e, a cada tick do job, processamos só TaskUsage.created_at >
watermark — incremental e idempotente (chave única por bucket agrega com +=).

Tempo de execução (run_seconds) é agregado a partir de AgentTask terminais
(completed|failed) cujo finished_at cai no mesmo lote incremental — usa o
started_at/finished_at da própria task, bucketado pelo dia UTC de finished_at.

Chamado por um job do APScheduler (settings.usage_rollup_interval_seconds)
registrado em main.py; também exposto para uso direto em testes.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.models import (
    AgentTask,
    TaskUsage,
    UsageRollupDaily,
    UsageRollupHourly,
    UsageRollupState,
    now,
)
from ryu.services.pricing import effective_cost_usd

WATERMARK_KEY = "usage"


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _hour_bucket(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H")


def _day_bucket(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


async def _get_or_create_state(db: AsyncSession) -> UsageRollupState:
    state = await db.get(UsageRollupState, WATERMARK_KEY)
    if state is None:
        state = UsageRollupState(key=WATERMARK_KEY, last_processed_at=None)
        db.add(state)
        await db.flush()
    return state


async def _apply_hourly(db: AsyncSession, key: tuple, agg: dict) -> None:
    workspace_id, bucket, agent_id, runtime, provider, model = key
    row = (
        await db.execute(
            select(UsageRollupHourly).where(
                UsageRollupHourly.workspace_id == workspace_id,
                UsageRollupHourly.bucket == bucket,
                UsageRollupHourly.agent_id == agent_id,
                UsageRollupHourly.runtime == runtime,
                UsageRollupHourly.provider == provider,
                UsageRollupHourly.model == model,
            )
        )
    ).scalars().first()
    if row is None:
        row = UsageRollupHourly(
            workspace_id=workspace_id, bucket=bucket, agent_id=agent_id,
            runtime=runtime, provider=provider, model=model,
            task_count=0, input_tokens=0, output_tokens=0,
            cache_read_tokens=0, cache_write_tokens=0,
            cost_usd_costed=0.0, cost_usd_estimated=0.0, uncosted_count=0,
        )
        db.add(row)
    row.task_count += agg["task_count"]
    row.input_tokens += agg["input_tokens"]
    row.output_tokens += agg["output_tokens"]
    row.cache_read_tokens += agg["cache_read_tokens"]
    row.cache_write_tokens += agg["cache_write_tokens"]
    row.cost_usd_costed += agg["cost_usd_costed"]
    row.cost_usd_estimated += agg["cost_usd_estimated"]
    row.uncosted_count += agg["uncosted_count"]


async def _apply_daily(db: AsyncSession, key: tuple, agg: dict) -> None:
    workspace_id, bucket, agent_id, runtime, provider, model = key
    row = (
        await db.execute(
            select(UsageRollupDaily).where(
                UsageRollupDaily.workspace_id == workspace_id,
                UsageRollupDaily.bucket == bucket,
                UsageRollupDaily.agent_id == agent_id,
                UsageRollupDaily.runtime == runtime,
                UsageRollupDaily.provider == provider,
                UsageRollupDaily.model == model,
            )
        )
    ).scalars().first()
    if row is None:
        row = UsageRollupDaily(
            workspace_id=workspace_id, bucket=bucket, agent_id=agent_id,
            runtime=runtime, provider=provider, model=model,
            task_count=0, input_tokens=0, output_tokens=0,
            cache_read_tokens=0, cache_write_tokens=0,
            cost_usd_costed=0.0, cost_usd_estimated=0.0, uncosted_count=0,
            run_seconds=0.0, run_task_count=0, run_failed_count=0,
        )
        db.add(row)
    row.task_count += agg.get("task_count", 0)
    row.input_tokens += agg.get("input_tokens", 0)
    row.output_tokens += agg.get("output_tokens", 0)
    row.cache_read_tokens += agg.get("cache_read_tokens", 0)
    row.cache_write_tokens += agg.get("cache_write_tokens", 0)
    row.cost_usd_costed += agg.get("cost_usd_costed", 0.0)
    row.cost_usd_estimated += agg.get("cost_usd_estimated", 0.0)
    row.uncosted_count += agg.get("uncosted_count", 0)
    row.run_seconds += agg.get("run_seconds", 0.0)
    row.run_task_count += agg.get("run_task_count", 0)
    row.run_failed_count += agg.get("run_failed_count", 0)


async def run_rollup(db: AsyncSession, *, batch_size: int = 5000) -> dict:
    """Processa TaskUsage novos desde o watermark e atualiza os rollups.

    Retorna um resumo {rows_processed, watermark}. Idempotente ao reexecutar
    sem novas linhas (rows_processed=0)."""
    state = await _get_or_create_state(db)
    since = _aware(state.last_processed_at)

    stmt = select(TaskUsage).order_by(TaskUsage.created_at).limit(batch_size)
    if since is not None:
        stmt = stmt.where(TaskUsage.created_at > since)
    rows = list((await db.execute(stmt)).scalars())

    if not rows:
        # ainda assim processa run-time de tasks terminais novas (fora do escopo
        # de TaskUsage, ex.: tasks sem usage reportado) usando o próprio watermark.
        pass

    # runtime por agent_id (cache) — usage rows já trazem workspace/agent mas
    # não runtime; olhamos AgentTask.agent_id -> Agent.runtime via join simples.
    agent_ids = {r.agent_id for r in rows}
    runtimes: dict[str, str] = {}
    if agent_ids:
        from ryu.models import Agent

        res = await db.execute(select(Agent.id, Agent.runtime).where(Agent.id.in_(agent_ids)))
        runtimes = {aid: rt or "" for aid, rt in res.all()}

    hourly: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))
    daily: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))
    max_created = since

    for r in rows:
        created = _aware(r.created_at) or now()
        if max_created is None or created > max_created:
            max_created = created
        runtime = getattr(r, "runtime", "") or runtimes.get(r.agent_id, "")
        cost, costed = effective_cost_usd(r)
        hkey = (r.workspace_id, _hour_bucket(created), r.agent_id, runtime, r.provider or "", r.model or "")
        dkey = (r.workspace_id, _day_bucket(created), r.agent_id, runtime, r.provider or "", r.model or "")
        for bucket, key in ((hourly, hkey), (daily, dkey)):
            b = bucket[key]
            b["task_count"] += 1
            b["input_tokens"] += r.input_tokens or 0
            b["output_tokens"] += r.output_tokens or 0
            b["cache_read_tokens"] += r.cache_read_tokens or 0
            b["cache_write_tokens"] += r.cache_write_tokens or 0
            if costed:
                b["cost_usd_costed"] += cost
            else:
                b["cost_usd_estimated"] += cost
                b["uncosted_count"] += 1

    for key, agg in hourly.items():
        await _apply_hourly(db, key, agg)
    for key, agg in daily.items():
        await _apply_daily(db, key, agg)

    # run-time (started_at/finished_at) das tasks terminais que caem na janela
    # processada — bucket por dia UTC de finished_at, dimensão runtime via agent.
    run_since = since
    if rows:
        run_stmt = select(AgentTask).where(
            AgentTask.status.in_(("completed", "failed")),
            AgentTask.finished_at.is_not(None),
            AgentTask.started_at.is_not(None),
        )
        if run_since is not None:
            run_stmt = run_stmt.where(AgentTask.finished_at > run_since)
        run_stmt = run_stmt.where(AgentTask.finished_at <= max_created) if max_created else run_stmt
        run_rows = list((await db.execute(run_stmt)).scalars())
        run_agent_ids = {t.agent_id for t in run_rows} - set(runtimes)
        if run_agent_ids:
            from ryu.models import Agent

            res = await db.execute(select(Agent.id, Agent.runtime).where(Agent.id.in_(run_agent_ids)))
            runtimes.update({aid: rt or "" for aid, rt in res.all()})
        run_daily: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))
        for t in run_rows:
            fin = _aware(t.finished_at)
            started = _aware(t.started_at)
            if fin is None or started is None:
                continue
            seconds = max(0.0, (fin - started).total_seconds())
            runtime = runtimes.get(t.agent_id, "")
            key = (t.workspace_id, _day_bucket(fin), t.agent_id, runtime, "", "")
            b = run_daily[key]
            b["run_seconds"] += seconds
            b["run_task_count"] += 1
            if t.status == "failed":
                b["run_failed_count"] += 1
        for key, agg in run_daily.items():
            await _apply_daily(db, key, agg)

    state.last_processed_at = max_created
    state.last_run_at = now()
    state.rows_processed = (state.rows_processed or 0) + len(rows)
    await db.commit()
    return {"rows_processed": len(rows), "watermark": max_created.isoformat() if max_created else None}
