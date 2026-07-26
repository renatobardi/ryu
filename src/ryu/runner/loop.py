"""Runner do Ryu — consome a fila AgentTask (tabela) e executa tasks.

Sem runtime LLM disponível no ambiente, a execução é um *stub executor*
determinístico: marca dispatched→running→completed, gera um result_summary,
comenta na issue (kind=issue) ou responde no chat (kind=chat, via
ryu.services.chat.handle_chat_task_done) e publica os eventos do hub.

Exports: start_runner(), stop_runner().
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select

from ryu.db import SessionLocal
from ryu.models import Agent, AgentTask, Issue, TaskMessage
from ryu.realtime.hub import hub
from ryu.services.auth import create_task_token
from ryu.services.chat import handle_chat_task_done

log = structlog.get_logger("ryu.runner")

POLL_INTERVAL = 2.0
LEASE_MINUTES = 30

_runner_task: asyncio.Task | None = None
_stopping = asyncio.Event()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _execute_real(db, task: AgentTask, agent: Agent) -> str | None:
    """Executa o CLI do runtime do agente num workspace isolado.

    Retorna o resumo, ou None se o runtime não está disponível (→ stub).
    Sem flags de bypass por default — veja adapters.py.
    """
    from ryu.config import settings
    from ryu.runner.adapters import build_command

    config = agent.runtime_config or {}
    argv = build_command(agent.runtime, task.prompt or "", config)
    if argv is None:
        return None

    workdir = settings.workspaces_root / task.id
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "PROMPT.md").write_text(task.prompt or "", encoding="utf-8")

    # skills anexadas ao agente → SKILLS.md
    from ryu.models import AgentSkill, Skill

    res = await db.execute(
        select(Skill).join(AgentSkill, AgentSkill.skill_id == Skill.id).where(AgentSkill.agent_id == agent.id)
    )
    skills = res.scalars().all()
    if skills:
        (workdir / "SKILLS.md").write_text(
            "\n\n---\n\n".join(f"# {s.name}\n{s.description}\n\n{s.content}" for s in skills),
            encoding="utf-8",
        )

    if config.get("repo_url"):
        clone = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth", "1", config["repo_url"], str(workdir / "repo"),
        )
        await clone.wait()

    import os

    env = {**os.environ, **(config.get("env") or {}), "RYU_TASK_ID": task.id, "RYU_AGENT_ID": agent.id}
    proc = await asyncio.create_subprocess_exec(
        *argv, cwd=str(workdir), env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    lines: list[str] = []

    async def _stream() -> None:
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            if not line:
                continue
            lines.append(line)
            db.add(TaskMessage(task_id=task.id, role="stdout", content=line[:4000]))
            await db.commit()
            await hub.publish(task.workspace_id, "task:progress", {"task_id": task.id, "line": line[:500]})

    try:
        await asyncio.wait_for(_stream(), timeout=30 * 60)
        await proc.wait()
    except asyncio.TimeoutError:
        proc.terminate()
        raise RuntimeError("timeout de 30min excedido")
    if proc.returncode != 0:
        raise RuntimeError(f"runtime saiu com código {proc.returncode}: {' '.join(lines[-5:])[:500]}")
    return "\n".join(lines[-50:]) or "(sem saída)"


async def _execute_stub(task: AgentTask, agent: Agent) -> str:
    """Execução simulada (nenhum runtime LLM configurado no ambiente)."""
    await asyncio.sleep(0.1)
    if task.kind == "chat":
        return (
            f"Olá! Aqui é o agente {agent.name} (@{agent.handle}). "
            "Recebi sua mensagem e processei o contexto da conversa. "
            "(runner em modo stub — configure um runtime LLM para respostas reais)"
        )
    first_line = (task.prompt or "").strip().splitlines()[0][:120] if task.prompt else ""
    return (
        f"Task processada pelo agente {agent.name} (@{agent.handle}) em modo stub. "
        f"Escopo: {first_line or '(sem prompt)'}. "
        "Configure um runtime LLM (runtime_config do agente) para execução real."
    )


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
            )
        except Exception:
            log.warning("runner_notify_failed", task_id=task.id)


async def _run_one(task_id: str) -> None:
    async with SessionLocal() as db:
        res = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
        task = res.scalars().first()
        if task is None or task.status != "queued":
            return
        res = await db.execute(select(Agent).where(Agent.id == task.agent_id))
        agent = res.scalars().first()
        if agent is None:
            task.status = "failed"
            task.error = "agent não encontrado"
            task.finished_at = _now()
            await db.commit()
            await hub.publish(task.workspace_id, "task:failed", {"task_id": task.id, "error": task.error})
            return

        # dispatched → running
        task.status = "running"
        task.started_at = _now()
        task.lease_expires_at = _now() + timedelta(minutes=LEASE_MINUTES)
        agent.status = "working"
        db.add(TaskMessage(task_id=task.id, role="system", content="runner: task iniciada (stub executor)"))
        await db.commit()
        await hub.publish(task.workspace_id, "task:running", {"task_id": task.id, "agent_id": agent.id})
        await hub.publish(task.workspace_id, "agent:status", {"agent_id": agent.id, "status": "working"})

        try:
            # token rat_ da execução (disponível para runtimes reais via env)
            try:
                await create_task_token(agent.id, task.id, task.workspace_id)
            except Exception:
                log.warning("runner_token_failed", task_id=task.id)

            result = await _execute_real(db, task, agent)
            if result is None:
                result = await _execute_stub(task, agent)
            task.result_summary = result
            task.status = "completed"
            task.finished_at = _now()
            agent.status = "idle"
            db.add(TaskMessage(task_id=task.id, role="progress", content="runner: task concluída"))
            await db.commit()

            if task.kind == "issue":
                await _finish_issue_task(db, task, agent)

            await hub.publish(
                task.workspace_id,
                "task:completed",
                {"task_id": task.id, "agent_id": agent.id, "kind": task.kind,
                 "issue_id": task.issue_id, "result_summary": task.result_summary},
            )
            await hub.publish(task.workspace_id, "agent:status", {"agent_id": agent.id, "status": "idle"})
        except Exception as exc:  # noqa: BLE001
            log.exception("runner_task_failed", task_id=task.id)
            task.status = "failed"
            task.error = str(exc)[:2000]
            task.finished_at = _now()
            agent.status = "error"
            await db.commit()
            await hub.publish(task.workspace_id, "task:failed", {"task_id": task.id, "error": task.error})
            await hub.publish(task.workspace_id, "agent:status", {"agent_id": agent.id, "status": "error"})

    # callback do chat (abre a própria sessão; task pode estar detached)
    if task.kind == "chat":
        try:
            await handle_chat_task_done(task)
        except Exception:
            log.exception("runner_chat_callback_failed", task_id=task.id)


async def _loop() -> None:
    log.info("runner_started")
    while not _stopping.is_set():
        try:
            async with SessionLocal() as db:
                res = await db.execute(
                    select(AgentTask.id)
                    .where(AgentTask.status == "queued")
                    .order_by(AgentTask.created_at)
                    .limit(5)
                )
                ids = [row[0] for row in res.all()]
            for tid in ids:
                if _stopping.is_set():
                    break
                await _run_one(tid)
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
            await asyncio.wait_for(_runner_task, timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            _runner_task.cancel()
        _runner_task = None
