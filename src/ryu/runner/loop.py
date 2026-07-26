"""Runner do Ryu — consome a fila AgentTask (tabela) e executa tasks.

Ciclo 1 (paridade multica):
- Execução CONCORRENTE: claim por agente respeitando agent.max_concurrent_tasks;
  tasks de agentes diferentes (e do mesmo agente até o limite) rodam em paralelo
  via asyncio tasks (multica service/task.go ClaimTask).
- Lease + heartbeat: lease_expires_at/last_heartbeat_at renovados durante a
  execução; sweeper periódico recupera tasks órfãs (running/dispatched com lease
  vencido → retry ou failed), aplica TTL de queued e limpa agentes presos em
  'working' (multica runtime_sweeper.go).
- Cancelamento efetivo: watchdog observa status/cancel_requested, mata o
  subprocesso e finaliza com commit guardado por status (cancel-ack), sem
  sobrescrever o cancelled (multica CancelTaskWithResult / AckTaskCancelled).
- Retry automático: falha de infraestrutura (crash/timeout/lease vencido)
  re-enfileira até max_attempts com failure_reason estruturado.
- Sessão/workdir: reusa work_dir e retoma sessão (--resume) em nova task da
  mesma issue/chat (multica 020_task_session); GC periódico de work_dirs de
  tasks terminadas (gc-check funcional: não apaga workdir reusável).
- Transcript estruturado: runtime claude roda com --output-format stream-json e
  cada evento vira TaskMessage tipada (assistant|tool_use|tool_result|system);
  usage (tokens/custo) do evento result é gravado em task_usage.

Sem runtime LLM disponível no ambiente, a execução é um *stub executor*
determinístico (marca completed, comenta na issue / responde no chat).

Exports: start_runner(), stop_runner().
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy import update as sql_update

from ryu.db import SessionLocal
from ryu.models import Agent, AgentTask, ChatSession, Issue, RuntimeProfile, TaskMessage
from ryu.realtime.hub import hub
from ryu.services import metrics as metrics_svc
from ryu.services.auth import create_task_token
from ryu.services.chat import handle_chat_task_done

log = structlog.get_logger("ryu.runner")

POLL_INTERVAL = 2.0

ACTIVE_STATUSES = ("queued", "dispatched", "running")
RETRYABLE_REASONS = ("crash", "timeout", "lease_expired")

_runner_task: asyncio.Task | None = None
_stopping = asyncio.Event()

# tasks em execução NESTE processo: task_id -> asyncio.Task / agent_id
_active: dict[str, asyncio.Task] = {}
_active_agents: dict[str, str] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _settings():
    from ryu.config import settings

    return settings


class TaskExecError(RuntimeError):
    """Falha de execução com razão estruturada (crash|timeout)."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass
class ExecResult:
    summary: str = ""
    cancelled: bool = False
    session_id: str | None = None
    usage: dict | None = None  # provider/model/input/output/cache_*/cost_usd


@dataclass
class _Seq:
    value: int = 0

    def next(self) -> int:
        self.value += 1
        return self.value


async def _seq_for(db, task_id: str) -> _Seq:
    res = await db.execute(select(TaskMessage.seq).where(TaskMessage.task_id == task_id))
    vals = [v or 0 for (v,) in res.all()]
    return _Seq(max(vals) if vals else 0)


async def _add_msg(
    db,
    task: AgentTask,
    seq: _Seq,
    *,
    role: str,
    content: str,
    type_: str = "",
    tool: str = "",
    input_: dict | None = None,
    output: dict | None = None,
    publish: bool = True,
) -> None:
    n = seq.next()
    db.add(
        TaskMessage(
            task_id=task.id,
            role=role,
            content=content[:8000],
            seq=n,
            type=type_ or role,
            tool=tool,
            input=input_,
            output=output,
        )
    )
    await db.commit()
    if publish:
        await hub.publish(
            task.workspace_id,
            "task:progress",
            {"task_id": task.id, "seq": n, "type": type_ or role, "tool": tool, "line": content[:500]},
        )


# ── Execução real (subprocesso do runtime) ────────────────────────────
async def _load_profile(db, agent: Agent) -> dict | None:
    pid = getattr(agent, "profile_id", None)
    if not pid:
        return None
    profile = await db.get(RuntimeProfile, pid)
    if profile is None:
        return None
    return {
        "protocol_family": profile.protocol_family,
        "command_name": profile.command_name,
        "fixed_args": list(profile.fixed_args or []),
    }


async def _resolve_workdir_session(db, task: AgentTask) -> tuple[Path, str | None]:
    """Reusa work_dir + session_id de task anterior da mesma issue/chat."""
    settings = _settings()
    if task.work_dir:  # rerun já pré-semeado
        return Path(task.work_dir), task.session_id
    prev = None
    if task.issue_id or task.chat_session_id:
        stmt = (
            select(AgentTask)
            .where(
                AgentTask.agent_id == task.agent_id,
                AgentTask.id != task.id,
                AgentTask.work_dir.is_not(None),
            )
            .order_by(AgentTask.created_at.desc())
            .limit(1)
        )
        if task.issue_id:
            stmt = stmt.where(AgentTask.issue_id == task.issue_id)
        else:
            stmt = stmt.where(AgentTask.chat_session_id == task.chat_session_id)
        prev = (await db.execute(stmt)).scalars().first()
    if prev is not None and prev.work_dir and Path(prev.work_dir).exists():
        return Path(prev.work_dir), task.session_id or prev.session_id
    return settings.workspaces_root / task.id, task.session_id


def _terminate(proc) -> None:
    with contextlib.suppress(ProcessLookupError):
        proc.terminate()


def _kill(proc) -> None:
    with contextlib.suppress(ProcessLookupError):
        proc.kill()


def _parse_stream_line(raw: str) -> dict | None:
    raw = raw.strip()
    if not raw.startswith("{"):
        return None
    try:
        ev = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return ev if isinstance(ev, dict) else None


async def _execute_real(db, task: AgentTask, agent: Agent) -> ExecResult | None:
    """Executa o CLI do runtime do agente num workspace isolado (ou reusado).

    Retorna ExecResult, ou None se o runtime não está disponível (→ stub).
    Sem flags de bypass por default — veja adapters.py.
    """
    from ryu.runner.adapters import build_command, runtime_env

    settings = _settings()
    config = agent.runtime_config or {}
    profile = await _load_profile(db, agent)
    workdir, resume_session = await _resolve_workdir_session(db, task)
    instructions = (getattr(agent, "instructions", "") or "").strip() or None
    structured = (profile or {}).get("protocol_family", agent.runtime) == "claude" and not config.get("command")

    def _argv(resume: str | None) -> list[str] | None:
        return build_command(
            agent.runtime,
            task.prompt or "",
            config,
            model=getattr(agent, "model", None),
            instructions=instructions,
            resume_session_id=resume,
            structured=structured,
            profile=profile,
        )

    argv = _argv(resume_session)
    if argv is None:
        return None

    workdir.mkdir(parents=True, exist_ok=True)
    task.work_dir = str(workdir)
    if resume_session:
        task.session_id = resume_session
    await db.commit()

    (workdir / "PROMPT.md").write_text(task.prompt or "", encoding="utf-8")
    if instructions:
        # AGENT.md no workdir (runtimes sem --append-system-prompt leem daqui)
        (workdir / "AGENT.md").write_text(instructions, encoding="utf-8")

    # skills anexadas ao agente → skills/<slug>/SKILL.md + arquivos de suporte
    # (paridade multica: cada skill vira um diretório com SKILL.md + skill_files)
    from ryu.models import AgentSkill, Skill, SkillFile
    from ryu.runner.builtin_skills import load_builtin_skills

    res = await db.execute(
        select(Skill).join(AgentSkill, AgentSkill.skill_id == Skill.id).where(AgentSkill.agent_id == agent.id)
    )
    skills = res.scalars().all()
    builtin_skills = load_builtin_skills()
    if skills or builtin_skills:
        skills_root = workdir / "skills"
        index_lines: list[str] = []
        for s in skills:
            slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in s.name.strip().lower().replace(" ", "-")) or s.id
            sdir = skills_root / slug
            sdir.mkdir(parents=True, exist_ok=True)
            fm = f"---\nname: {s.name}\ndescription: {(s.description or '').replace(chr(10), ' ')}\n---\n\n"
            (sdir / "SKILL.md").write_text(fm + (s.content or ""), encoding="utf-8")
            fres = await db.execute(select(SkillFile).where(SkillFile.skill_id == s.id))
            for sf in fres.scalars():
                rel = Path(sf.path)
                if rel.is_absolute() or ".." in rel.parts:
                    continue  # nunca escreve fora do diretório da skill
                dest = sdir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(sf.content or "", encoding="utf-8")
            desc = f" — {s.description}" if s.description else ""
            index_lines.append(f"- {s.name}: skills/{slug}/SKILL.md{desc}")
        # skills built-in de plataforma (paridade multica: sempre acrescentadas
        # por cima das skills de workspace do agente — task.go:3777 BuiltinSkills())
        for bs in builtin_skills:
            sdir = skills_root / bs.slug
            sdir.mkdir(parents=True, exist_ok=True)
            (sdir / "SKILL.md").write_text(bs.content, encoding="utf-8")
            for bf in bs.files:
                rel = Path(bf.path)
                if rel.is_absolute() or ".." in rel.parts:
                    continue  # nunca escreve fora do diretório da skill
                dest = sdir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(bf.content, encoding="utf-8")
            index_lines.append(f"- {bs.slug} (built-in): skills/{bs.slug}/SKILL.md")
        (workdir / "SKILLS.md").write_text(
            "# Skills disponíveis\n\nCada skill vive em skills/<nome>/SKILL.md com seus arquivos de apoio.\n"
            "As skills built-in de plataforma (prefixo ryu-) são entregues a todo agente,\n"
            "por cima das skills de workspace.\n\n"
            + "\n".join(index_lines),
            encoding="utf-8",
        )

    if config.get("repo_url") and not (workdir / "repo").exists():
        clone = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth", "1", config["repo_url"], str(workdir / "repo"),
        )
        await clone.wait()

    import os

    env = {
        **os.environ,
        **runtime_env(
            agent.runtime,
            thinking_level=getattr(agent, "thinking_level", None),
            service_tier=getattr(agent, "service_tier", None),
        ),
        **(config.get("env") or {}),
        "RYU_TASK_ID": task.id,
        "RYU_AGENT_ID": agent.id,
    }

    seq = await _seq_for(db, task.id)
    cancel_event = asyncio.Event()
    state: dict = {"lines": [], "texts": [], "session_id": None, "result": None, "usage": None}

    async def _handle_structured(ev: dict) -> None:
        etype = ev.get("type")
        if ev.get("session_id"):
            state["session_id"] = ev["session_id"]
        if etype == "system":
            sub = ev.get("subtype", "")
            await _add_msg(db, task, seq, role="system", type_="system",
                           content=f"runtime: {sub or 'system'}" + (f" model={ev.get('model')}" if ev.get("model") else ""))
        elif etype == "assistant":
            for block in (ev.get("message") or {}).get("content") or []:
                btype = block.get("type")
                if btype == "text" and block.get("text"):
                    state["texts"].append(block["text"])
                    await _add_msg(db, task, seq, role="assistant", type_="assistant", content=block["text"])
                elif btype == "tool_use":
                    await _add_msg(
                        db, task, seq, role="tool_use", type_="tool_use",
                        tool=str(block.get("name") or ""), input_=block.get("input") or {},
                        content=f"→ {block.get('name')}",
                    )
        elif etype == "user":
            for block in (ev.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    out = block.get("content")
                    if not isinstance(out, (dict, list)):
                        out = {"text": str(out)[:4000]}
                    await _add_msg(
                        db, task, seq, role="tool_result", type_="tool_result",
                        tool=str(block.get("tool_use_id") or ""), output=out if isinstance(out, dict) else {"blocks": out},
                        content=str(block.get("content"))[:2000],
                    )
        elif etype == "result":
            state["result"] = ev.get("result") or ""
            usage = ev.get("usage") or {}
            state["usage"] = {
                "provider": "anthropic",
                "model": getattr(agent, "model", None) or ev.get("model") or "claude",
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
                "cache_write_tokens": usage.get("cache_creation_input_tokens", 0),
                "cost_usd": ev.get("total_cost_usd", 0.0) or 0.0,
            }

    async def _run_proc(cmd: list[str]) -> int:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(workdir), env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )

        async def _stream() -> None:
            assert proc.stdout is not None
            async for raw in proc.stdout:
                line = raw.decode(errors="replace").rstrip()
                if not line:
                    continue
                state["lines"].append(line)
                ev = _parse_stream_line(line) if structured else None
                if ev is not None:
                    try:
                        await _handle_structured(ev)
                    except Exception:
                        log.warning("runner_stream_event_failed", task_id=task.id)
                else:
                    await _add_msg(db, task, seq, role="stdout", type_="stdout", content=line[:4000])

        async def _watchdog() -> None:
            """Heartbeat/lease + observa cancelamento pedido via API."""
            hb = max(5, settings.task_heartbeat_seconds)
            try:
                while proc.returncode is None:
                    await asyncio.sleep(hb)
                    if proc.returncode is not None:
                        return
                    async with SessionLocal() as wdb:
                        row = (
                            await wdb.execute(
                                select(AgentTask.status, AgentTask.cancel_requested).where(AgentTask.id == task.id)
                            )
                        ).first()
                        status, cancel_req = (row[0], row[1]) if row else ("cancelled", True)
                        if status == "cancelled" or cancel_req:
                            cancel_event.set()
                            _terminate(proc)
                            await asyncio.sleep(5)
                            if proc.returncode is None:
                                _kill(proc)
                            return
                        await wdb.execute(
                            sql_update(AgentTask)
                            .where(AgentTask.id == task.id, AgentTask.status == "running")
                            .values(
                                last_heartbeat_at=_now(),
                                lease_expires_at=_now() + timedelta(minutes=settings.task_lease_minutes),
                            )
                        )
                        await wdb.commit()
            except asyncio.CancelledError:
                pass

        wd = asyncio.create_task(_watchdog())
        try:
            await asyncio.wait_for(_stream(), timeout=settings.task_run_timeout_minutes * 60)
            await proc.wait()
        except asyncio.TimeoutError:
            _terminate(proc)
            await asyncio.sleep(2)
            _kill(proc)
            with contextlib.suppress(Exception):
                await proc.wait()
            if not cancel_event.is_set():
                raise TaskExecError("timeout", f"timeout de {settings.task_run_timeout_minutes}min excedido")
        finally:
            wd.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await wd
        return proc.returncode if proc.returncode is not None else -1

    rc = await _run_proc(argv)
    if rc != 0 and not cancel_event.is_set() and resume_session:
        # sessão do runtime pode ter se perdido (container novo) — tenta sem --resume
        log.warning("runner_resume_failed_retrying", task_id=task.id, session_id=resume_session)
        retry_argv = _argv(None)
        if retry_argv is not None:
            state["lines"].clear()
            rc = await _run_proc(retry_argv)

    summary = (state["result"] or "").strip() or "\n".join(state["texts"][-10:]).strip() or "\n".join(state["lines"][-50:]) or "(sem saída)"
    if cancel_event.is_set():
        return ExecResult(summary=summary, cancelled=True, session_id=state["session_id"], usage=state["usage"])
    if rc != 0:
        raise TaskExecError("crash", f"runtime saiu com código {rc}: {' '.join(state['lines'][-5:])[:500]}")
    return ExecResult(summary=summary, session_id=state["session_id"], usage=state["usage"])


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


async def _guarded_finish(db, task_id: str, from_status: str, values: dict) -> bool:
    """UPDATE ... WHERE status=<from_status>. Retorna True se aplicou."""
    res = await db.execute(
        sql_update(AgentTask).where(AgentTask.id == task_id, AgentTask.status == from_status).values(**values)
    )
    await db.commit()
    return (res.rowcount or 0) > 0


async def _ack_cancelled(db, task: AgentTask, agent: Agent | None, seq: _Seq, partial_summary: str = "") -> None:
    """Cancel-ack: garante cancelled no banco, registra transcript parcial e
    finaliza a mensagem de chat pendente (multica AckTaskCancelled)."""
    await db.execute(
        sql_update(AgentTask)
        .where(AgentTask.id == task.id, AgentTask.status.in_(("dispatched", "running")))
        .values(status="cancelled", cancel_requested=True, finished_at=_now())
    )
    if partial_summary:
        await db.execute(
            sql_update(AgentTask)
            .where(AgentTask.id == task.id, AgentTask.status == "cancelled", AgentTask.result_summary == "")
            .values(result_summary=partial_summary[:4000])
        )
    await db.commit()
    task.status = "cancelled"
    with contextlib.suppress(Exception):
        await _add_msg(db, task, seq, role="system", type_="system",
                       content="runner: task cancelada — subprocesso terminado (cancel-ack)", publish=False)
    if agent is not None:
        await _recompute_agent_status(db, agent.id)
    with contextlib.suppress(Exception):
        metrics_svc.task_terminal("cancelled")
    await hub.publish(task.workspace_id, "task:cancelled", {"task_id": task.id, "ack": True})


async def _run_one(task_id: str) -> None:
    settings = _settings()
    task: AgentTask | None = None
    async with SessionLocal() as db:
        res = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
        task = res.scalars().first()
        if task is None or task.status not in ("queued", "dispatched"):
            return
        seq = await _seq_for(db, task.id)
        res = await db.execute(select(Agent).where(Agent.id == task.agent_id))
        agent = res.scalars().first()
        if agent is None:
            task.status = "failed"
            task.error = "agent não encontrado"
            task.failure_reason = "agent_missing"
            task.finished_at = _now()
            await db.commit()
            await hub.publish(task.workspace_id, "task:failed", {"task_id": task.id, "error": task.error})
            return
        if getattr(agent, "archived_at", None):
            task.status = "cancelled"
            task.failure_reason = "agent_archived"
            task.finished_at = _now()
            await db.commit()
            await hub.publish(task.workspace_id, "task:cancelled", {"task_id": task.id, "reason": "agent_archived"})
            return
        if task.cancel_requested:
            task.status = "cancelled"
            task.finished_at = _now()
            await db.commit()
            await hub.publish(task.workspace_id, "task:cancelled", {"task_id": task.id})
            return

        # (queued|dispatched) → running
        task.status = "running"
        task.started_at = _now()
        task.lease_expires_at = _now() + timedelta(minutes=settings.task_lease_minutes)
        task.last_heartbeat_at = _now()
        agent.status = "working"
        await db.commit()
        with contextlib.suppress(Exception):
            metrics_svc.task_dispatched()
            wait = None
            if task.created_at and task.started_at:
                wait = (_aware(task.started_at) - _aware(task.created_at)).total_seconds()
            metrics_svc.task_started(queue_wait_seconds=wait)
        await _add_msg(
            db, task, seq, role="system", type_="system",
            content=f"runner: task iniciada (attempt {task.attempt or 1}/{task.max_attempts or settings.task_default_max_attempts})",
            publish=False,
        )
        await hub.publish(task.workspace_id, "task:running", {"task_id": task.id, "agent_id": agent.id, "attempt": task.attempt or 1})
        await hub.publish(task.workspace_id, "agent:status", {"agent_id": agent.id, "status": "working"})

        try:
            # token rat_ da execução (disponível para runtimes reais via env)
            try:
                await create_task_token(agent.id, task.id, task.workspace_id)
            except Exception:
                log.warning("runner_token_failed", task_id=task.id)

            exec_res = await _execute_real(db, task, agent)
            if exec_res is None:
                exec_res = ExecResult(summary=await _execute_stub(task, agent))

            if exec_res.cancelled:
                await _ack_cancelled(db, task, agent, seq, partial_summary=exec_res.summary)
            else:
                finished = _now()
                applied = await _guarded_finish(
                    db,
                    task.id,
                    "running",
                    {
                        "status": "completed",
                        "result_summary": exec_res.summary,
                        "error": "",
                        "finished_at": finished,
                        "session_id": exec_res.session_id or task.session_id,
                        "lease_expires_at": None,
                    },
                )
                if not applied:
                    # cancelada por fora enquanto terminávamos — preserva cancelled
                    await _ack_cancelled(db, task, agent, seq, partial_summary=exec_res.summary)
                else:
                    task.status = "completed"
                    task.result_summary = exec_res.summary
                    task.finished_at = finished
                    if exec_res.session_id:
                        task.session_id = exec_res.session_id
                    if exec_res.usage:
                        try:
                            from ryu.services import agents as agents_svc

                            await agents_svc.record_task_usage(db, task, **exec_res.usage)
                        except Exception:
                            log.warning("runner_usage_record_failed", task_id=task.id)
                    await _add_msg(db, task, seq, role="progress", type_="system",
                                   content="runner: task concluída", publish=False)
                    with contextlib.suppress(Exception):
                        run_seconds = None
                        if task.started_at and task.finished_at:
                            run_seconds = (_aware(task.finished_at) - _aware(task.started_at)).total_seconds()
                        metrics_svc.task_terminal("completed", run_seconds=run_seconds)
                    if task.kind == "issue":
                        await _finish_issue_task(db, task, agent)
                    await _recompute_agent_status(db, agent.id)
                    await hub.publish(
                        task.workspace_id,
                        "task:completed",
                        {"task_id": task.id, "agent_id": agent.id, "kind": task.kind,
                         "issue_id": task.issue_id, "result_summary": task.result_summary},
                    )
        except Exception as exc:  # noqa: BLE001
            reason = getattr(exc, "reason", "crash")
            attempt = task.attempt or 1
            max_attempts = task.max_attempts or settings.task_default_max_attempts
            retryable = reason in RETRYABLE_REASONS and attempt < max_attempts
            log.exception("runner_task_failed", task_id=task.id, reason=reason, attempt=attempt, retry=retryable)
            if retryable:
                applied = await _guarded_finish(
                    db,
                    task.id,
                    "running",
                    {
                        "status": "queued",
                        "attempt": attempt + 1,
                        "failure_reason": reason,
                        "error": str(exc)[:2000],
                        "lease_expires_at": None,
                        "started_at": None,
                        "last_heartbeat_at": None,
                    },
                )
                if applied:
                    task.status = "queued"
                    with contextlib.suppress(Exception):
                        await _add_msg(db, task, seq, role="system", type_="system",
                                       content=f"runner: falha de infraestrutura ({reason}) — re-enfileirada "
                                               f"(attempt {attempt + 1}/{max_attempts})", publish=False)
                    await _recompute_agent_status(db, agent.id)
                    await hub.publish(task.workspace_id, "task:queued",
                                      {"task_id": task.id, "retry": True, "attempt": attempt + 1})
                else:
                    await _ack_cancelled(db, task, agent, seq)
            else:
                applied = await _guarded_finish(
                    db,
                    task.id,
                    "running",
                    {
                        "status": "failed",
                        "failure_reason": reason,
                        "error": str(exc)[:2000],
                        "finished_at": _now(),
                        "lease_expires_at": None,
                    },
                )
                if applied:
                    task.status = "failed"
                    task.error = str(exc)[:2000]
                    with contextlib.suppress(Exception):
                        metrics_svc.task_terminal("failed", reason=reason)
                    await _recompute_agent_status(db, agent.id, error=True)
                    await hub.publish(task.workspace_id, "task:failed", {"task_id": task.id, "error": task.error, "failure_reason": reason})
                else:
                    await _ack_cancelled(db, task, agent, seq)

    # callback do chat (abre a própria sessão; task pode estar detached)
    if task is not None and task.kind == "chat" and task.status in ("completed", "failed", "cancelled"):
        try:
            await handle_chat_task_done(task)
        except Exception:
            log.exception("runner_chat_callback_failed", task_id=task.id)


# ── Claim concorrente por agente ──────────────────────────────────────
def _spawn(task_id: str, agent_id: str) -> None:
    if task_id in _active:
        return
    at = asyncio.get_event_loop().create_task(_run_one(task_id))
    _active[task_id] = at
    _active_agents[task_id] = agent_id

    def _done(_t: asyncio.Task, tid: str = task_id) -> None:
        _active.pop(tid, None)
        _active_agents.pop(tid, None)

    at.add_done_callback(_done)


async def _claim_and_spawn() -> None:
    settings = _settings()
    if getattr(settings, "runner_mode", "auto") == "off":
        return  # execução só via daemons externos (claim pela API /api/daemon)
    if len(_active) >= settings.runner_max_parallel:
        return
    claimed: list[tuple[str, str]] = []
    async with SessionLocal() as db:
        res = await db.execute(
            select(AgentTask).where(AgentTask.status == "queued").order_by(AgentTask.created_at).limit(50)
        )
        queued = [t for t in res.scalars() if t.id not in _active]
        if not queued:
            return
        # modo auto: cede tasks cujo provider tem runtime externo ONLINE no
        # workspace (daemon executa na máquina do usuário — multica)
        external_pairs: set[tuple[str, str]] = set()
        if getattr(settings, "runner_mode", "auto") == "auto":
            try:
                from ryu.services.daemon import online_providers

                external_pairs = await online_providers(db)
            except Exception:
                external_pairs = set()
        # contagem de execuções em andamento por agente (multica CountRunningTasks)
        counts: dict[str, int] = {}
        for agid in _active_agents.values():
            counts[agid] = counts.get(agid, 0) + 1
        res = await db.execute(
            select(AgentTask.id, AgentTask.agent_id).where(AgentTask.status.in_(("dispatched", "running")))
        )
        for tid, agid in res.all():
            if tid not in _active:  # órfã de outro processo/restart — conta mesmo assim
                counts[agid] = counts.get(agid, 0) + 1
        agents: dict[str, Agent | None] = {}
        for t in queued:
            if len(_active) + len(claimed) >= settings.runner_max_parallel:
                break
            if t.agent_id not in agents:
                agents[t.agent_id] = await db.get(Agent, t.agent_id)
            agent = agents[t.agent_id]
            # agente inexistente/arquivado: claim mesmo assim — _run_one finaliza a task
            limit = max(1, (agent.max_concurrent_tasks or 1)) if agent else 1
            if agent is not None and not getattr(agent, "archived_at", None):
                if (t.workspace_id, agent.runtime) in external_pairs:
                    continue  # daemon externo online executa este provider
                if counts.get(t.agent_id, 0) >= limit:
                    continue
            t.status = "dispatched"
            t.lease_expires_at = _now() + timedelta(minutes=settings.task_lease_minutes)
            counts[t.agent_id] = counts.get(t.agent_id, 0) + 1
            claimed.append((t.id, t.agent_id))
        await db.commit()
    for tid, agid in claimed:
        _spawn(tid, agid)


# ── Sweeper (recuperação de órfãs) ────────────────────────────────────
async def _sweep() -> None:
    """multica runtime_sweeper.go: leases vencidos, TTL de queued, agentes presos."""
    settings = _settings()
    now = _now()
    events: list[tuple[str, str, dict]] = []  # (workspace_id, event, data)
    touched_agents: set[str] = set()
    async with SessionLocal() as db:
        # (a) running/dispatched com lease vencido (não são deste processo)
        res = await db.execute(
            select(AgentTask).where(AgentTask.status.in_(("dispatched", "running")))
        )
        for t in res.scalars():
            if t.id in _active:
                continue
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
                events.append((t.workspace_id, "task:queued", {"task_id": t.id, "retry": True, "attempt": t.attempt}))
            else:
                t.status = "cancelled" if t.cancel_requested else "failed"
                t.failure_reason = "lease_expired"
                t.error = t.error or "lease vencido — processo do runner caiu durante a execução"
                t.finished_at = now
                ev = "task:cancelled" if t.status == "cancelled" else "task:failed"
                events.append((t.workspace_id, ev, {"task_id": t.id, "failure_reason": "lease_expired"}))
            db.add(TaskMessage(task_id=t.id, role="system", type="system", seq=0,
                               content=f"sweeper: lease vencido → {t.status}"))

        # (b) queued: TTL + agente arquivado/inexistente
        cutoff = now - timedelta(hours=settings.task_queued_ttl_hours)
        res = await db.execute(select(AgentTask).where(AgentTask.status == "queued"))
        agents_cache: dict[str, Agent | None] = {}
        for t in res.scalars():
            if t.id in _active:
                continue
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
        for agent in res.scalars():
            touched_agents.add(agent.id)
    for wid, ev, data in events:
        await hub.publish(wid, ev, data)
    async with SessionLocal() as db:
        for agent_id in touched_agents:
            # não mexe em agentes com execução ativa neste processo
            if agent_id in _active_agents.values():
                continue
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
    log.info("runner_started", max_parallel=settings.runner_max_parallel)
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
            await _claim_and_spawn()
        except Exception:
            log.exception("runner_loop_error")
        try:
            await asyncio.wait_for(_stopping.wait(), timeout=POLL_INTERVAL)
        except asyncio.TimeoutError:
            pass
    # drena execuções ativas com um prazo curto
    pending = list(_active.values())
    if pending:
        done, still = await asyncio.wait(pending, timeout=10)
        for t in still:
            t.cancel()
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
