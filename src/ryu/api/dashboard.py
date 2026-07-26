"""API do domínio USAGE-OBSERVABILITY (dashboards de tokens/custo/runtime).

`router`: montar em main.py com prefix="/api/dashboard".

Endpoints (paridade multica router.go:1299-1313, 1363/1366):
- GET /usage/daily        — tokens/custo por dia, dimensão provider+model
- GET /usage/by-agent     — idem, por agente
- GET /usage/by-hour      — distribuição por hora-do-dia (heatmap 0..23)
- GET /agent-runtime      — total_seconds/task_count/failed_count por agente
- GET /runtime/daily      — idem, por dia
- GET /runtimes/{id}/usage, /runtimes/{id}/usage/by-agent — usage por runtime
- GET /agent-activity-30d — atividade diária por agente (30 dias)
- GET /agent-run-counts   — contagem de runs por agente

Todos aceitam ?workspace_id, ?project_id (quando fizer sentido) e ?tz
(nome IANA; default UTC) — o corte de "dia" é feito no timezone do viewer.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import get_db
from ryu.models import Agent, AgentTask, Issue, TaskUsage, User
from ryu.services.auth import current_user
from ryu.services.pricing import effective_cost_usd

router = APIRouter()


def _tzinfo(tz: str | None):
    if not tz:
        return timezone.utc
    try:
        return ZoneInfo(tz)
    except Exception:
        return timezone.utc


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _day_key(dt: datetime, tz) -> str:
    return _aware(dt).astimezone(tz).date().isoformat()


async def _project_issue_ids(db: AsyncSession, workspace_id: str, project_id: str | None) -> set[str] | None:
    if not project_id:
        return None
    rows = await db.execute(
        select(Issue.id).where(Issue.workspace_id == workspace_id, Issue.project_id == project_id)
    )
    return {r for (r,) in rows.all()}


# ── Usage: daily / by-agent / by-hour (gap core #19, #21) ──────────────
@router.get("/usage/daily")
async def usage_daily(
    workspace_id: str,
    days: int = 30,
    project_id: str | None = None,
    tz: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    days = max(1, min(days, 365))
    tzinfo = _tzinfo(tz)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    issue_ids = await _project_issue_ids(db, workspace_id, project_id)

    rows = (
        await db.execute(
            select(TaskUsage, AgentTask.issue_id)
            .join(AgentTask, AgentTask.id == TaskUsage.task_id)
            .where(TaskUsage.workspace_id == workspace_id, TaskUsage.created_at >= since)
        )
    ).all()

    def _bucket():
        return {
            "task_count": 0, "input_tokens": 0, "output_tokens": 0,
            "cache_read_tokens": 0, "cache_write_tokens": 0,
            "cost_usd_costed": 0.0, "cost_usd_estimated": 0.0, "uncosted_count": 0,
        }

    by_day: dict[str, dict] = {}
    for u, issue_id in rows:
        if issue_ids is not None and issue_id not in issue_ids:
            continue
        day = _day_key(u.created_at, tzinfo)
        b = by_day.setdefault(day, _bucket())
        cost, costed = effective_cost_usd(u)
        b["task_count"] += 1
        b["input_tokens"] += u.input_tokens or 0
        b["output_tokens"] += u.output_tokens or 0
        b["cache_read_tokens"] += u.cache_read_tokens or 0
        b["cache_write_tokens"] += u.cache_write_tokens or 0
        if costed:
            b["cost_usd_costed"] += cost
        else:
            b["cost_usd_estimated"] += cost
            b["uncosted_count"] += 1
    for b in by_day.values():
        b["cost_usd_costed"] = round(b["cost_usd_costed"], 6)
        b["cost_usd_estimated"] = round(b["cost_usd_estimated"], 6)
    return {
        "workspace_id": workspace_id, "days": days, "tz": tz or "UTC", "project_id": project_id,
        "by_day": [{"day": d, **b} for d, b in sorted(by_day.items(), reverse=True)],
    }


@router.get("/usage/by-agent")
async def usage_by_agent(
    workspace_id: str,
    days: int = 30,
    project_id: str | None = None,
    tz: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    issue_ids = await _project_issue_ids(db, workspace_id, project_id)

    rows = (
        await db.execute(
            select(TaskUsage, AgentTask.issue_id)
            .join(AgentTask, AgentTask.id == TaskUsage.task_id)
            .where(TaskUsage.workspace_id == workspace_id, TaskUsage.created_at >= since)
        )
    ).all()
    agents = list((await db.execute(select(Agent).where(Agent.workspace_id == workspace_id))).scalars())
    names = {a.id: a.name for a in agents}
    runtimes = {a.id: a.runtime for a in agents}

    def _bucket():
        return {
            "task_count": 0, "input_tokens": 0, "output_tokens": 0,
            "cache_read_tokens": 0, "cache_write_tokens": 0,
            "cost_usd_costed": 0.0, "cost_usd_estimated": 0.0, "uncosted_count": 0,
        }

    by_agent: dict[str, dict] = {}
    by_provider_model: dict[tuple, dict] = {}
    for u, issue_id in rows:
        if issue_ids is not None and issue_id not in issue_ids:
            continue
        cost, costed = effective_cost_usd(u)
        for store, key in ((by_agent, u.agent_id), (by_provider_model, (u.agent_id, u.provider, u.model))):
            b = store.setdefault(key, _bucket())
            b["task_count"] += 1
            b["input_tokens"] += u.input_tokens or 0
            b["output_tokens"] += u.output_tokens or 0
            b["cache_read_tokens"] += u.cache_read_tokens or 0
            b["cache_write_tokens"] += u.cache_write_tokens or 0
            if costed:
                b["cost_usd_costed"] += cost
            else:
                b["cost_usd_estimated"] += cost
                b["uncosted_count"] += 1
    out = []
    for aid, b in sorted(by_agent.items(), key=lambda kv: -(kv[1]["cost_usd_costed"] + kv[1]["cost_usd_estimated"])):
        models = [
            {"provider": p, "model": m, **v}
            for (a2, p, m), v in by_provider_model.items() if a2 == aid
        ]
        out.append({
            "agent_id": aid, "agent_name": names.get(aid, aid), "runtime": runtimes.get(aid, ""),
            **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in b.items()},
            "by_provider_model": models,
        })
    return {"workspace_id": workspace_id, "days": days, "project_id": project_id, "by_agent": out}


@router.get("/usage/by-hour")
async def usage_by_hour(
    workspace_id: str,
    days: int = 30,
    tz: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """Heatmap de atividade — distribuição de tasks/tokens por hora-do-dia (0..23)."""
    days = max(1, min(days, 365))
    tzinfo = _tzinfo(tz)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await db.execute(
            select(TaskUsage).where(TaskUsage.workspace_id == workspace_id, TaskUsage.created_at >= since)
        )
    ).scalars()
    by_hour: dict[int, dict] = {h: {"task_count": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0} for h in range(24)}
    for u in rows:
        hour = _aware(u.created_at).astimezone(tzinfo).hour
        cost, _ = effective_cost_usd(u)
        b = by_hour[hour]
        b["task_count"] += 1
        b["input_tokens"] += u.input_tokens or 0
        b["output_tokens"] += u.output_tokens or 0
        b["cost_usd"] += cost
    for b in by_hour.values():
        b["cost_usd"] = round(b["cost_usd"], 6)
    return {
        "workspace_id": workspace_id, "days": days, "tz": tz or "UTC",
        "by_hour": [{"hour": h, **by_hour[h]} for h in range(24)],
    }


# ── Runtime (tempo de execução) — gap core #18 ──────────────────────────
async def _runtime_rows(db: AsyncSession, workspace_id: str, days: int, project_id: str | None):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    issue_ids = await _project_issue_ids(db, workspace_id, project_id)
    stmt = select(AgentTask).where(
        AgentTask.workspace_id == workspace_id,
        AgentTask.status.in_(("completed", "failed")),
        AgentTask.started_at.is_not(None),
        AgentTask.finished_at.is_not(None),
        AgentTask.created_at >= since,
    )
    tasks = list((await db.execute(stmt)).scalars())
    if issue_ids is not None:
        tasks = [t for t in tasks if t.issue_id in issue_ids]
    return tasks


@router.get("/agent-runtime")
async def agent_runtime(
    workspace_id: str,
    days: int = 30,
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    days = max(1, min(days, 365))
    tasks = await _runtime_rows(db, workspace_id, days, project_id)
    agents = list((await db.execute(select(Agent).where(Agent.workspace_id == workspace_id))).scalars())
    names = {a.id: a.name for a in agents}
    by_agent: dict[str, dict] = {}
    for t in tasks:
        b = by_agent.setdefault(t.agent_id, {"total_seconds": 0.0, "task_count": 0, "failed_count": 0})
        b["total_seconds"] += (_aware(t.finished_at) - _aware(t.started_at)).total_seconds()
        b["task_count"] += 1
        if t.status == "failed":
            b["failed_count"] += 1
    out = [
        {"agent_id": aid, "agent_name": names.get(aid, aid), **{k: (round(v, 3) if isinstance(v, float) else v) for k, v in b.items()}}
        for aid, b in sorted(by_agent.items(), key=lambda kv: -kv[1]["total_seconds"])
    ]
    return {"workspace_id": workspace_id, "days": days, "project_id": project_id, "by_agent": out}


@router.get("/runtime/daily")
async def runtime_daily(
    workspace_id: str,
    days: int = 30,
    project_id: str | None = None,
    tz: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    days = max(1, min(days, 365))
    tzinfo = _tzinfo(tz)
    tasks = await _runtime_rows(db, workspace_id, days, project_id)
    by_day: dict[str, dict] = {}
    for t in tasks:
        day = _day_key(t.finished_at, tzinfo)
        b = by_day.setdefault(day, {"total_seconds": 0.0, "task_count": 0, "failed_count": 0})
        b["total_seconds"] += (_aware(t.finished_at) - _aware(t.started_at)).total_seconds()
        b["task_count"] += 1
        if t.status == "failed":
            b["failed_count"] += 1
    return {
        "workspace_id": workspace_id, "days": days, "tz": tz or "UTC",
        "by_day": [
            {"day": d, **{k: (round(v, 3) if isinstance(v, float) else v) for k, v in b.items()}}
            for d, b in sorted(by_day.items(), reverse=True)
        ],
    }


# ── Usage por runtime (agent.runtime) — gap important #21 ───────────────
@router.get("/runtimes/{runtime}/usage")
async def runtime_usage(
    runtime: str,
    workspace_id: str,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    agent_ids = {
        a for (a,) in (
            await db.execute(select(Agent.id).where(Agent.workspace_id == workspace_id, Agent.runtime == runtime))
        ).all()
    }
    rows = (
        await db.execute(
            select(TaskUsage).where(TaskUsage.workspace_id == workspace_id, TaskUsage.created_at >= since)
        )
    ).scalars()
    by_day: dict[str, dict] = {}
    for u in rows:
        if u.agent_id not in agent_ids and (getattr(u, "runtime", "") or "") != runtime:
            continue
        day = u.created_at.date().isoformat()
        b = by_day.setdefault(day, {"task_count": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
        cost, _ = effective_cost_usd(u)
        b["task_count"] += 1
        b["input_tokens"] += u.input_tokens or 0
        b["output_tokens"] += u.output_tokens or 0
        b["cost_usd"] += cost
    for b in by_day.values():
        b["cost_usd"] = round(b["cost_usd"], 6)
    return {
        "workspace_id": workspace_id, "runtime": runtime, "days": days,
        "by_day": [{"day": d, **b} for d, b in sorted(by_day.items(), reverse=True)],
    }


# ── Atividade de agentes no workspace — gap important #25 ───────────────
@router.get("/agent-activity-30d")
async def agent_activity_30d(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    since = datetime.now(timezone.utc) - timedelta(days=30)
    rows = (
        await db.execute(
            select(AgentTask.agent_id, AgentTask.created_at).where(
                AgentTask.workspace_id == workspace_id, AgentTask.created_at >= since
            )
        )
    ).all()
    by_agent_day: dict[str, dict[str, int]] = {}
    for agent_id, created_at in rows:
        day = created_at.date().isoformat()
        d = by_agent_day.setdefault(agent_id, {})
        d[day] = d.get(day, 0) + 1
    return {
        "workspace_id": workspace_id,
        "since": since.date().isoformat(),
        "activity": [
            {"agent_id": aid, "days": [{"day": d, "count": c} for d, c in sorted(days.items())]}
            for aid, days in by_agent_day.items()
        ],
    }


@router.get("/agent-run-counts")
async def agent_run_counts(
    workspace_id: str,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await db.execute(
            select(AgentTask.agent_id, AgentTask.status).where(
                AgentTask.workspace_id == workspace_id, AgentTask.created_at >= since
            )
        )
    ).all()
    agents = list((await db.execute(select(Agent).where(Agent.workspace_id == workspace_id))).scalars())
    names = {a.id: a.name for a in agents}
    counts: dict[str, dict] = {}
    for agent_id, status in rows:
        c = counts.setdefault(agent_id, {"total": 0, "completed": 0, "failed": 0})
        c["total"] += 1
        if status in ("completed", "failed"):
            c[status] += 1
    return {
        "workspace_id": workspace_id, "days": days,
        "counts": [
            {"agent_id": aid, "agent_name": names.get(aid, aid), **c}
            for aid, c in sorted(counts.items(), key=lambda kv: -kv[1]["total"])
        ],
    }
