"""Serviço do domínio AGENTS + TASKS (ciclo 1).

Exporta:
- can_manage_agent / can_invoke_agent / ensure_can_invoke: permissão de
  gerenciamento e de invocação (permission_mode private|public_to + allow-list
  agent_invocation_target, equivalente funcional do multica
  130_agent_invocation_permission).
- archive_agent / restore_agent / cancel_tasks_for_agent: soft-delete com
  cancelamento em lote das tasks pendentes (multica 031_agent_archive).
- record_task_usage / task_usage_rows / usage_summary: registro por
  (task, provider, model) e agregação simples (multica 032_task_usage).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.models import (
    Agent,
    AgentInvocationTarget,
    AgentTask,
    Member,
    TaskUsage,
    now,
)
from ryu.realtime.hub import hub

ACTIVE_TASK_STATUSES = ("queued", "dispatched", "running")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_archived(agent: Agent) -> bool:
    return getattr(agent, "archived_at", None) is not None


# ── Permissões ────────────────────────────────────────────────────────
async def _member_role(db: AsyncSession, user_id: str, workspace_id: str) -> str | None:
    res = await db.execute(
        select(Member).where(Member.workspace_id == workspace_id, Member.user_id == user_id)
    )
    m = res.scalars().first()
    return m.role if m else None


async def can_manage_agent(db: AsyncSession, user_id: str, agent: Agent) -> bool:
    """Dono (created_by) ou admin/owner do workspace. Agentes: só o próprio."""
    if user_id.startswith("agent:"):
        return user_id == f"agent:{agent.id}"
    if agent.created_by is None:
        return True  # legado: agente sem dono é gerenciável por qualquer membro
    if agent.created_by == user_id:
        return True
    role = await _member_role(db, user_id, agent.workspace_id)
    return role in ("owner", "admin")


async def can_invoke_agent(db: AsyncSession, user_id: str, agent: Agent) -> bool:
    """canInvokeAgent do multica: arquivado nunca; private = só o dono;
    public_to = allow-list (sem targets = workspace inteiro)."""
    if is_archived(agent):
        return False
    if user_id.startswith("agent:"):
        return True  # agente→agente (squads/delegação) sempre pode
    if agent.created_by is None:
        return True  # legado
    if agent.created_by == user_id:
        return True
    role = await _member_role(db, user_id, agent.workspace_id)
    if role in ("owner", "admin"):
        return True
    if role is None:
        return False  # nem membro do workspace
    mode = getattr(agent, "permission_mode", None) or "public_to"
    if mode == "private":
        return False
    # public_to: allow-list
    res = await db.execute(
        select(AgentInvocationTarget).where(AgentInvocationTarget.agent_id == agent.id)
    )
    targets = list(res.scalars())
    if not targets:
        return True  # sem allow-list = aberto ao workspace
    member = await db.execute(
        select(Member).where(Member.workspace_id == agent.workspace_id, Member.user_id == user_id)
    )
    member_row = member.scalars().first()
    for t in targets:
        if t.target_type == "workspace" and t.target_id in (agent.workspace_id, "", "*"):
            return True
        if t.target_type == "member" and t.target_id in (
            user_id,
            member_row.id if member_row else None,
        ):
            return True
    return False


async def ensure_can_invoke(db: AsyncSession, user_id: str, agent: Agent) -> None:
    if is_archived(agent):
        raise HTTPException(409, "agente arquivado não pode ser invocado")
    if not await can_invoke_agent(db, user_id, agent):
        raise HTTPException(403, "sem permissão para invocar este agente")


# ── Archive / cancel-tasks ────────────────────────────────────────────
async def cancel_tasks_for_agent(
    db: AsyncSession, agent_id: str, *, reason: str = "agent_archived"
) -> list[str]:
    """Cancela tasks queued/dispatched/running do agente.

    Tasks running recebem status cancelled + cancel_requested — o runner
    observa e mata o subprocesso (o commit de finalização dele é guardado
    por status e não sobrescreve).  Publica task:cancelled por task.
    """
    res = await db.execute(
        select(AgentTask).where(
            AgentTask.agent_id == agent_id, AgentTask.status.in_(ACTIVE_TASK_STATUSES)
        )
    )
    tasks = list(res.scalars())
    cancelled: list[str] = []
    for t in tasks:
        t.status = "cancelled"
        t.cancel_requested = True
        t.failure_reason = reason
        t.finished_at = now()
        cancelled.append(t.id)
    await db.commit()
    for t in tasks:
        await hub.publish(t.workspace_id, "task:cancelled", {"task_id": t.id, "reason": reason})
    return cancelled


async def archive_agent(db: AsyncSession, agent: Agent, archived_by: str) -> list[str]:
    agent.archived_at = now()
    agent.archived_by = archived_by
    agent.status = "offline"
    await db.commit()
    cancelled = await cancel_tasks_for_agent(db, agent.id, reason="agent_archived")
    await hub.publish(agent.workspace_id, "agent:status", {"agent_id": agent.id, "status": "offline", "archived": True})
    return cancelled


async def restore_agent(db: AsyncSession, agent: Agent) -> None:
    agent.archived_at = None
    agent.archived_by = None
    agent.status = "idle"
    await db.commit()
    await hub.publish(agent.workspace_id, "agent:status", {"agent_id": agent.id, "status": "idle", "archived": False})


# ── Usage ─────────────────────────────────────────────────────────────
async def record_task_usage(
    db: AsyncSession,
    task: AgentTask,
    *,
    provider: str = "",
    model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    cost_usd: float = 0.0,
    runtime: str = "",
) -> TaskUsage:
    """Grava linha em task_usage e acumula nos totais da task.

    Custo autoritativo (cost_usd > 0, ex.: reportado pelo runtime/daemon) é
    preservado como está (costed=True). Sem custo reportado, tenta estimar
    via pricing table (usage-observability ciclo 1); modelo desconhecido
    fica uncosted (costed=False, cost_usd=0.0) — nunca chuta preço.
    """
    from ryu.services.pricing import estimate_cost_usd

    reported = float(cost_usd or 0.0)
    costed = reported > 0
    final_cost = reported
    if not costed:
        est = estimate_cost_usd(
            provider or "", model or "",
            int(input_tokens or 0), int(output_tokens or 0),
            int(cache_read_tokens or 0), int(cache_write_tokens or 0),
        )
        if est is not None:
            final_cost = est
            costed = True  # preço estimado a partir da tabela (não autoritativo, mas "costed")

    rt = runtime or ""
    if not rt:
        agent = await db.get(Agent, task.agent_id)
        rt = getattr(agent, "runtime", "") if agent else ""

    row = TaskUsage(
        task_id=task.id,
        workspace_id=task.workspace_id,
        agent_id=task.agent_id,
        provider=provider or "",
        model=model or "",
        input_tokens=int(input_tokens or 0),
        output_tokens=int(output_tokens or 0),
        cache_read_tokens=int(cache_read_tokens or 0),
        cache_write_tokens=int(cache_write_tokens or 0),
        cost_usd=float(final_cost or 0.0),
        runtime=rt,
        costed=costed,
    )
    db.add(row)
    task.input_tokens = (task.input_tokens or 0) + row.input_tokens
    task.output_tokens = (task.output_tokens or 0) + row.output_tokens
    task.cost_usd = round((task.cost_usd or 0.0) + row.cost_usd, 6)
    await db.commit()

    try:
        from ryu.services import metrics as metrics_svc

        metrics_svc.llm_usage(
            provider or "", model or "",
            input_tokens=int(input_tokens or 0), output_tokens=int(output_tokens or 0),
            cache_read_tokens=int(cache_read_tokens or 0), cache_write_tokens=int(cache_write_tokens or 0),
            cost_usd=float(final_cost or 0.0),
            cost_source="provider" if reported > 0 else "estimated",
            unpriced=not costed,
        )
    except Exception:
        pass
    return row


def usage_to_dict(u: TaskUsage) -> dict:
    return {
        "id": u.id,
        "task_id": u.task_id,
        "workspace_id": u.workspace_id,
        "agent_id": u.agent_id,
        "provider": u.provider,
        "model": u.model,
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_read_tokens": u.cache_read_tokens,
        "cache_write_tokens": u.cache_write_tokens,
        "cost_usd": u.cost_usd,
        "runtime": getattr(u, "runtime", ""),
        "costed": getattr(u, "costed", True),
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


async def task_usage_rows(db: AsyncSession, task_id: str) -> list[TaskUsage]:
    res = await db.execute(
        select(TaskUsage).where(TaskUsage.task_id == task_id).order_by(TaskUsage.created_at)
    )
    return list(res.scalars())


async def usage_summary(
    db: AsyncSession, workspace_id: str, *, agent_id: str | None = None, days: int = 30
) -> dict:
    """Agregação simples de task_usage por agente e por provider/model."""
    since = _now() - timedelta(days=days)
    stmt = select(TaskUsage).where(
        TaskUsage.workspace_id == workspace_id, TaskUsage.created_at >= since
    )
    if agent_id:
        stmt = stmt.where(TaskUsage.agent_id == agent_id)
    rows = list((await db.execute(stmt)).scalars())

    def _bucket() -> dict:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "cost_usd": 0.0,
            "records": 0,
        }

    totals = _bucket()
    by_agent: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    by_day: dict[str, dict] = {}
    for u in rows:
        model_key = f"{u.provider or 'unknown'}/{u.model or 'unknown'}"
        day = u.created_at.date().isoformat() if u.created_at else "unknown"
        for b in (
            totals,
            by_agent.setdefault(u.agent_id, _bucket()),
            by_model.setdefault(model_key, _bucket()),
            by_day.setdefault(day, _bucket()),
        ):
            b["input_tokens"] += u.input_tokens or 0
            b["output_tokens"] += u.output_tokens or 0
            b["cache_read_tokens"] += u.cache_read_tokens or 0
            b["cache_write_tokens"] += u.cache_write_tokens or 0
            b["cost_usd"] = round(b["cost_usd"] + (u.cost_usd or 0.0), 6)
            b["records"] += 1
    return {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "days": days,
        "since": since.isoformat(),
        "totals": totals,
        "by_agent": [{"agent_id": k, **v} for k, v in by_agent.items()],
        "by_model": [{"model": k, **v} for k, v in by_model.items()],
        "by_day": [{"day": k, **v} for k, v in sorted(by_day.items(), reverse=True)],
    }
