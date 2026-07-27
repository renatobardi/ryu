"""Runner do Ryu — scheduler, sweeper de lease, TTL, retry e GC de work_dirs.

Responsabilidade do servidor (ADR-0001):
- Scheduler: acorda daemons conectados quando há tasks na fila e runtime
  externo online para o provider.
- Sweeper: recupera tasks órfãs (running/dispatched com lease vencido),
  aplica TTL de queued e limpa agentes presos em 'working'.
- GC de work_dirs: remove diretórios de tasks terminadas há mais de N dias.
- Retry: falhas de infraestrutura (crash/timeout/lease_expired) re-enfileira
  até max_attempts.

O Daemon é o único executor de tasks. Sem runtime externo online a task
permanece `queued`; nenhum comentário é escrito na issue sem execução real.

Exports: start_runner(), stop_runner().
"""
from __future__ import annotations

import asyncio
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog
from sqlalchemy import select

from ryu.db import SessionLocal
from ryu.models import Agent, AgentTask, ChatSession, Issue, TaskMessage
from ryu.realtime.hub import hub

log = structlog.get_logger("ryu.runner")

POLL_INTERVAL = 2.0

ACTIVE_STATUSES = ("queued", "dispatched", "running")
RETRYABLE_REASONS = ("crash", "timeout", "lease_expired")

_runner_task: asyncio.Task | None = None
_stopping = asyncio.Event()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _settings():
    from ryu.config import settings

    return settings


async def _recompute_agent_status(db, agent_id: str, *, error: bool = False) -> None:
    agent = await db.get(Agent, agent_id)
    if agent is None:
        return
    res = await db.execute(
        select(AgentTask.id).where(
            AgentTask.agent_id == agent_id, AgentTask.status.in_(("dispatched", "running"))
        )
    )
    active = len(res.all())
    if getattr(agent, "archived_at", None):
        new = "offline"
    elif active > 0:
        new = "working"
    else:
        new = "error" if error else "idle"
    if agent.status != new:
        agent.status = new
        await db.commit()
        await hub.publish(agent.workspace_id, "agent:status", {"agent_id": agent_id, "status": new})
    else:
        await db.commit()


async def _finish_issue_task(db, task: AgentTask, agent: Agent) -> None:
    """Comenta o resultado na issue e move para in_review."""
    if not task.issue_id:
        return
    res = await db.execute(select(Issue).where(Issue.id == task.issue_id))
    issue = res.scalars().first()
    if issue is None:
        return
    # import tardio para evitar ciclo issues -> (nada) ; issues não importa runner
    from ryu.services import issues as issues_svc

    try:
        await issues_svc.create_comment(db, issue.id, "agent", agent.id, task.result_summary)
    except Exception:
        log.warning("runner_comment_failed", task_id=task.id)
    if issue.status in ("todo", "in_progress"):
        try:
            await issues_svc.update_issue(db, issue.id, "agent", agent.id, {"status": "in_review"})
        except Exception:
            log.warning("runner_issue_move_failed", task_id=task.id)
    # notifica o criador (se for membro)
    if issue.creator_type == "member" and issue.creator_id and not issue.creator_id.startswith("agent:"):
        try:
            from ryu.services.inbox import notify

            await notify(
                db,
                issue.workspace_id,
                issue.creator_id,
                "attention",
                f"{issue.key} pronta para revisão",
                f"O agente {agent.name} finalizou a task e comentou na issue.",
                issue_id=issue.id,
                group="agent_activity",
            )
        except Exception:
            log.warning("runner_notify_failed", task_id=task.id)


# ── Scheduler (acorda daemons conectados) ─────────────────────────────
async def _schedule() -> None:
    """Varre a fila e notifica daemons conectados quando há fila + runtime online.

    O claim real continua sendo feito pelo daemon via /api/daemon/tasks/claim;
    o servidor só faz o wakeup periódico para reduzir a latência.
    """
    from ryu.services.daemon import daemon_hub, online_providers

    async with SessionLocal() as db:
        res = await db.execute(
            select(AgentTask.workspace_id, Agent.runtime)
            .join(Agent, Agent.id == AgentTask.agent_id)
            .where(AgentTask.status == "queued")
            .distinct()
        )
        pending = {(wid, runtime) for (wid, runtime) in res.all()}
        if not pending:
            return
        try:
            pairs = await online_providers(db)
        except Exception:
            log.warning("runner_schedule_online_providers_failed")
            return

    for wid, runtime in pending:
        if (wid, runtime) in pairs:
            try:
                await daemon_hub.notify_task_available(wid, {"workspace_id": wid})
            except Exception:
                log.warning("runner_schedule_wakeup_failed", workspace_id=wid, runtime=runtime)


# ── Sweeper (recuperação de órfãs) ────────────────────────────────────
async def _sweep() -> None:
    """multica runtime_sweeper.go: leases vencidos, TTL de queued, agentes presos."""
    settings = _settings()
    now = _now()
    events: list[tuple[str, str, dict]] = []  # (workspace_id, event, data)
    touched_agents: set[str] = set()
    async with SessionLocal() as db:
        # (a) running/dispatched com lease vencido (órfãs de daemons)
        res = await db.execute(
            select(AgentTask).where(AgentTask.status.in_(("dispatched", "running")))
        )
        for t in res.scalars():
            lease = _aware(t.lease_expires_at) or (
                (_aware(t.updated_at) or now) + timedelta(minutes=settings.task_lease_minutes)
            )
            if lease > now:
                continue
            touched_agents.add(t.agent_id)
            attempt = t.attempt or 1
            max_attempts = t.max_attempts or settings.task_default_max_attempts
            if not t.cancel_requested and attempt < max_attempts:
                t.status = "queued"
                t.attempt = attempt + 1
                t.failure_reason = "lease_expired"
                t.error = "lease vencido — execução órfã recuperada"
                t.lease_expires_at = None
                t.started_at = None
                t.last_heartbeat_at = None
                t.runtime_id = None
                events.append(
                    (t.workspace_id, "task:queued", {"task_id": t.id, "retry": True, "attempt": t.attempt})
                )
            else:
                t.status = "cancelled" if t.cancel_requested else "failed"
                t.failure_reason = "lease_expired"
                t.error = t.error or "lease vencido — execução caiu durante a execução"
                t.finished_at = now
                ev = "task:cancelled" if t.status == "cancelled" else "task:failed"
                events.append((t.workspace_id, ev, {"task_id": t.id, "failure_reason": "lease_expired"}))
            db.add(
                TaskMessage(task_id=t.id, role="system", type="system", seq=0,
                            content=f"sweeper: lease vencido → {t.status}")
            )

        # (b) queued: TTL + agente arquivado/inexistente
        cutoff = now - timedelta(hours=settings.task_queued_ttl_hours)
        res = await db.execute(select(AgentTask).where(AgentTask.status == "queued"))
        agents_cache: dict[str, Agent | None] = {}
        for t in res.scalars():
            if t.agent_id not in agents_cache:
                agents_cache[t.agent_id] = await db.get(Agent, t.agent_id)
            agent = agents_cache[t.agent_id]
            reason = None
            if agent is None:
                reason = "agent_missing"
            elif getattr(agent, "archived_at", None):
                reason = "agent_archived"
            elif (_aware(t.created_at) or now) < cutoff:
                reason = "queued_ttl"
            if reason:
                t.status = "cancelled"
                t.failure_reason = reason
                t.finished_at = now
                events.append((t.workspace_id, "task:cancelled", {"task_id": t.id, "reason": reason}))
        await db.commit()

        # (c) agentes presos em 'working' sem tasks ativas
        res = await db.execute(select(Agent).where(Agent.status == "working"))
        for working in res.scalars():
            touched_agents.add(working.id)
    for wid, ev, data in events:
        await hub.publish(wid, ev, data)
    async with SessionLocal() as db:
        for agent_id in touched_agents:
            await _recompute_agent_status(db, agent_id)


# ── GC de work_dirs ───────────────────────────────────────────────────
async def _gc_workdirs() -> None:
    """Remove work_dirs de tasks terminadas há mais de N dias, preservando
    diretórios reusáveis (issue aberta / chat ativo) — gc-check funcional."""
    settings = _settings()
    root = Path(settings.workspaces_root)
    if not root.exists():
        return
    cutoff = _now() - timedelta(days=settings.workdir_gc_days)
    async with SessionLocal() as db:
        for d in list(root.iterdir()):
            if not d.is_dir():
                continue
            res = await db.execute(
                select(AgentTask).where((AgentTask.work_dir == str(d)) | (AgentTask.id == d.name))
            )
            tasks = list(res.scalars())
            if not tasks:
                try:
                    mtime = datetime.fromtimestamp(d.stat().st_mtime, tz=timezone.utc)
                except OSError:
                    continue
                if mtime < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
                    log.info("runner_gc_removed_orphan_dir", path=str(d))
                continue
            keep = False
            for t in tasks:
                if t.status in ACTIVE_STATUSES:
                    keep = True
                    break
                fin = _aware(t.finished_at or t.updated_at or t.created_at)
                if fin is not None and fin > cutoff:
                    keep = True
                    break
                # gc-check: workdir reusável por issue aberta / chat vivo não é apagado
                if t.issue_id:
                    issue = await db.get(Issue, t.issue_id)
                    if issue is not None and issue.status not in ("done", "cancelled"):
                        keep = True
                        break
                if t.chat_session_id:
                    cs = await db.get(ChatSession, t.chat_session_id)
                    if cs is not None and not cs.archived:
                        keep = True
                        break
            if not keep:
                shutil.rmtree(d, ignore_errors=True)
                log.info("runner_gc_removed_workdir", path=str(d), tasks=len(tasks))


# ── Loop principal ────────────────────────────────────────────────────
async def _loop() -> None:
    settings = _settings()
    log.info("runner_started")
    last_sweep = 0.0
    last_gc = 0.0
    # recuperação pós-restart: sweep imediato
    try:
        await _sweep()
        last_sweep = time.monotonic()
    except Exception:
        log.exception("runner_initial_sweep_failed")
    while not _stopping.is_set():
        try:
            mono = time.monotonic()
            if mono - last_sweep >= settings.sweep_interval_seconds:
                await _sweep()
                last_sweep = mono
            if mono - last_gc >= settings.workdir_gc_interval_seconds:
                await _gc_workdirs()
                last_gc = mono
            await _schedule()
        except Exception:
            log.exception("runner_loop_error")
        try:
            await asyncio.wait_for(_stopping.wait(), timeout=POLL_INTERVAL)
        except asyncio.TimeoutError:
            pass
    log.info("runner_stopped")


def start_runner() -> None:
    global _runner_task
    if _runner_task is not None and not _runner_task.done():
        return
    _stopping.clear()
    _runner_task = asyncio.get_event_loop().create_task(_loop())


async def stop_runner() -> None:
    global _runner_task
    _stopping.set()
    if _runner_task is not None:
        try:
            await asyncio.wait_for(_runner_task, timeout=15)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            _runner_task.cancel()
        _runner_task = None
