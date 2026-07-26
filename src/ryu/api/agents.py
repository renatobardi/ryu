"""API do domínio AGENTS + TASKS (fila de execução).

- `router`: montar com prefix="/api/agents"
- `tasks_router`: montar com prefix="/api/tasks"
- `pages_router`: página /w/{slug}/agents, montar SEM prefixo

Ciclo 1: permissão de invocação (permission_mode + allow-list), archive/restore,
cancel-tasks, filtro issue_id + active-task/runs/rerun, usage por task,
transcript estruturado, configuração de execução (instructions/model/...).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import get_db
from ryu.models import (
    Agent,
    AgentInvocationTarget,
    AgentTask,
    Issue,
    TaskMessage,
    User,
    Workspace,
    now,
)
from ryu.realtime.hub import hub
from ryu.services import agents as agents_svc
from ryu.services.auth import current_user

router = APIRouter()
tasks_router = APIRouter()
pages_router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

AGENT_STATUSES = ["idle", "working", "blocked", "error", "offline"]
PERMISSION_MODES = ["private", "public_to"]
THINKING_LEVELS = ["none", "low", "medium", "high"]
SERVICE_TIERS = ["standard", "flex", "priority"]
TARGET_TYPES = ["workspace", "member"]


def agent_to_dict(a: Agent) -> dict:
    return {
        "id": a.id,
        "workspace_id": a.workspace_id,
        "name": a.name,
        "handle": a.handle,
        "description": a.description,
        "runtime": a.runtime,
        "runtime_config": a.runtime_config,
        "status": a.status,
        "max_concurrent_tasks": a.max_concurrent_tasks,
        "created_by": a.created_by,
        "visibility": a.visibility,
        "permission_mode": a.permission_mode,
        "archived_at": a.archived_at.isoformat() if a.archived_at else None,
        "archived_by": a.archived_by,
        "instructions": a.instructions,
        "model": a.model,
        "thinking_level": a.thinking_level,
        "service_tier": a.service_tier,
        "profile_id": a.profile_id,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def task_to_dict(t: AgentTask) -> dict:
    return {
        "id": t.id,
        "workspace_id": t.workspace_id,
        "agent_id": t.agent_id,
        "issue_id": t.issue_id,
        "chat_session_id": t.chat_session_id,
        "kind": t.kind,
        "status": t.status,
        "prompt": t.prompt,
        "result_summary": t.result_summary,
        "error": t.error,
        "failure_reason": t.failure_reason,
        "attempt": t.attempt,
        "max_attempts": t.max_attempts,
        "retry_of_task_id": t.retry_of_task_id,
        "rerun_of_task_id": t.rerun_of_task_id,
        "session_id": t.session_id,
        "work_dir": t.work_dir,
        "cancel_requested": t.cancel_requested,
        "started_at": t.started_at.isoformat() if t.started_at else None,
        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
        "last_heartbeat_at": t.last_heartbeat_at.isoformat() if t.last_heartbeat_at else None,
        "lease_expires_at": t.lease_expires_at.isoformat() if t.lease_expires_at else None,
        "input_tokens": t.input_tokens,
        "output_tokens": t.output_tokens,
        "cost_usd": t.cost_usd,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


class AgentCreate(BaseModel):
    workspace_id: str
    name: str
    handle: str = ""
    description: str = ""
    runtime: str = "claude"
    runtime_config: dict = {}
    max_concurrent_tasks: int = 1
    permission_mode: str = "public_to"
    instructions: str = ""
    model: str | None = None
    thinking_level: str | None = None
    service_tier: str | None = None
    profile_id: str | None = None


class AgentUpdate(BaseModel):
    name: str | None = None
    handle: str | None = None
    description: str | None = None
    runtime: str | None = None
    runtime_config: dict | None = None
    status: str | None = None
    max_concurrent_tasks: int | None = None
    permission_mode: str | None = None
    instructions: str | None = None
    model: str | None = None
    thinking_level: str | None = None
    service_tier: str | None = None
    profile_id: str | None = None


class TargetIn(BaseModel):
    target_type: str  # workspace|member
    target_id: str


class TargetsPut(BaseModel):
    targets: list[TargetIn] = []


class UsageIn(BaseModel):
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0


async def _get_agent(db: AsyncSession, agent_id: str) -> Agent:
    res = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = res.scalars().first()
    if agent is None:
        raise HTTPException(404, "agent não encontrado")
    return agent


async def _require_manage(db: AsyncSession, user: User, agent: Agent) -> None:
    if not await agents_svc.can_manage_agent(db, user.id, agent):
        raise HTTPException(403, "apenas o dono do agente ou admin do workspace pode gerenciá-lo")


def _validate_agent_fields(changes: dict) -> None:
    if changes.get("status") is not None and changes["status"] not in AGENT_STATUSES:
        raise HTTPException(422, f"status inválido: {changes['status']}")
    if changes.get("permission_mode") is not None and changes["permission_mode"] not in PERMISSION_MODES:
        raise HTTPException(422, f"permission_mode inválido: {changes['permission_mode']}")
    if changes.get("thinking_level") is not None and changes["thinking_level"] not in THINKING_LEVELS:
        raise HTTPException(422, f"thinking_level inválido: {changes['thinking_level']}")
    if changes.get("service_tier") is not None and changes["service_tier"] not in SERVICE_TIERS:
        raise HTTPException(422, f"service_tier inválido: {changes['service_tier']}")
    if changes.get("max_concurrent_tasks") is not None and changes["max_concurrent_tasks"] < 1:
        raise HTTPException(422, "max_concurrent_tasks deve ser >= 1")


async def _validate_profile(db: AsyncSession, profile_id: str | None, workspace_id: str) -> None:
    if not profile_id:
        return
    from ryu.models import RuntimeProfile

    profile = await db.get(RuntimeProfile, profile_id)
    if profile is None or profile.workspace_id != workspace_id:
        raise HTTPException(404, "runtime profile não encontrado neste workspace")


# ── Agents CRUD ───────────────────────────────────────────────────────
@router.post("", status_code=201)
async def create_agent(payload: AgentCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    changes = payload.model_dump()
    _validate_agent_fields(changes)
    await _validate_profile(db, payload.profile_id, payload.workspace_id)
    handle = (payload.handle or payload.name).strip().lstrip("@").lower().replace(" ", "-")
    agent = Agent(
        workspace_id=payload.workspace_id,
        name=payload.name.strip(),
        handle=handle,
        description=payload.description,
        runtime=payload.runtime,
        runtime_config=payload.runtime_config or {},
        max_concurrent_tasks=payload.max_concurrent_tasks,
        created_by=None if user.id.startswith("agent:") else user.id,
        permission_mode=payload.permission_mode,
        instructions=payload.instructions or "",
        model=payload.model,
        thinking_level=payload.thinking_level,
        service_tier=payload.service_tier,
        profile_id=payload.profile_id,
    )
    db.add(agent)
    await db.commit()
    await hub.publish(agent.workspace_id, "agent:status", {"agent_id": agent.id, "status": agent.status})
    return agent_to_dict(agent)


@router.get("")
async def list_agents(
    workspace_id: str,
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = select(Agent).where(Agent.workspace_id == workspace_id)
    if not include_archived:
        stmt = stmt.where(Agent.archived_at.is_(None))
    res = await db.execute(stmt.order_by(Agent.name))
    return [agent_to_dict(a) for a in res.scalars()]


@router.get("/{agent_id}")
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    return agent_to_dict(await _get_agent(db, agent_id))


@router.patch("/{agent_id}")
async def update_agent(agent_id: str, payload: AgentUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    agent = await _get_agent(db, agent_id)
    await _require_manage(db, user, agent)
    changes = {k: getattr(payload, k) for k in payload.model_fields_set}
    _validate_agent_fields(changes)
    if "profile_id" in changes:
        await _validate_profile(db, changes["profile_id"], agent.workspace_id)
    for k, v in changes.items():
        setattr(agent, k, v)
    await db.commit()
    if "status" in changes:
        await hub.publish(agent.workspace_id, "agent:status", {"agent_id": agent.id, "status": agent.status})
    return agent_to_dict(agent)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    agent = await _get_agent(db, agent_id)
    await _require_manage(db, user, agent)
    # cancela pendências antes do hard delete (evita task órfã rodando)
    await agents_svc.cancel_tasks_for_agent(db, agent.id, reason="agent_deleted")
    await db.delete(agent)
    await db.commit()
    return Response(status_code=204)


# ── Archive / restore / cancel-tasks (multica 031_agent_archive) ──────
@router.post("/{agent_id}/archive")
async def archive_agent(agent_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    agent = await _get_agent(db, agent_id)
    await _require_manage(db, user, agent)
    if agent.archived_at is not None:
        raise HTTPException(409, "agent já arquivado")
    cancelled = await agents_svc.archive_agent(db, agent, archived_by=user.id)
    return {**agent_to_dict(agent), "cancelled_task_ids": cancelled}


@router.post("/{agent_id}/restore")
async def restore_agent(agent_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    agent = await _get_agent(db, agent_id)
    await _require_manage(db, user, agent)
    if agent.archived_at is None:
        raise HTTPException(409, "agent não está arquivado")
    await agents_svc.restore_agent(db, agent)
    return agent_to_dict(agent)


@router.post("/{agent_id}/cancel-tasks")
async def cancel_agent_tasks(agent_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    agent = await _get_agent(db, agent_id)
    await _require_manage(db, user, agent)
    cancelled = await agents_svc.cancel_tasks_for_agent(db, agent.id, reason="cancelled_by_user")
    return {"cancelled_task_ids": cancelled, "count": len(cancelled)}


# ── Invocation targets (multica 130_agent_invocation_permission) ──────
@router.get("/{agent_id}/invocation-targets")
async def list_invocation_targets(agent_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    agent = await _get_agent(db, agent_id)
    res = await db.execute(
        select(AgentInvocationTarget).where(AgentInvocationTarget.agent_id == agent.id)
    )
    return [
        {"id": t.id, "agent_id": t.agent_id, "target_type": t.target_type, "target_id": t.target_id}
        for t in res.scalars()
    ]


@router.put("/{agent_id}/invocation-targets")
async def put_invocation_targets(
    agent_id: str, payload: TargetsPut, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    agent = await _get_agent(db, agent_id)
    await _require_manage(db, user, agent)
    for t in payload.targets:
        if t.target_type not in TARGET_TYPES:
            raise HTTPException(422, f"target_type inválido: {t.target_type}")
    res = await db.execute(select(AgentInvocationTarget).where(AgentInvocationTarget.agent_id == agent.id))
    for old in res.scalars():
        await db.delete(old)
    rows = [
        AgentInvocationTarget(agent_id=agent.id, target_type=t.target_type, target_id=t.target_id)
        for t in payload.targets
    ]
    for r in rows:
        db.add(r)
    await db.commit()
    return [
        {"id": r.id, "agent_id": r.agent_id, "target_type": r.target_type, "target_id": r.target_id}
        for r in rows
    ]


# ── Tasks (fila) ──────────────────────────────────────────────────────
@tasks_router.get("")
async def list_tasks(
    workspace_id: str,
    status: str | None = None,
    agent_id: str | None = None,
    issue_id: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = select(AgentTask).where(AgentTask.workspace_id == workspace_id)
    if status:
        stmt = stmt.where(AgentTask.status == status)
    if agent_id:
        stmt = stmt.where(AgentTask.agent_id == agent_id)
    if issue_id:
        stmt = stmt.where(AgentTask.issue_id == issue_id)
    if kind:
        stmt = stmt.where(AgentTask.kind == kind)
    stmt = stmt.order_by(AgentTask.created_at.desc()).limit(min(limit, 200))
    res = await db.execute(stmt)
    return [task_to_dict(t) for t in res.scalars()]


# rotas estáticas ANTES de /{task_id}
@tasks_router.get("/usage/summary")
async def usage_summary(
    workspace_id: str,
    agent_id: str | None = None,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    return await agents_svc.usage_summary(db, workspace_id, agent_id=agent_id, days=days)


# ── Tasks por issue: active-task, histórico e rerun ───────────────────
async def _get_issue(db: AsyncSession, issue_id: str) -> Issue:
    issue = await db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(404, "issue não encontrada")
    return issue


@tasks_router.get("/issues/{issue_id}/active")
async def issue_active_task(issue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await _get_issue(db, issue_id)
    res = await db.execute(
        select(AgentTask)
        .where(AgentTask.issue_id == issue_id, AgentTask.status.in_(agents_svc.ACTIVE_TASK_STATUSES))
        .order_by(AgentTask.created_at.desc())
        .limit(1)
    )
    task = res.scalars().first()
    return {"task": task_to_dict(task) if task else None}


@tasks_router.get("/issues/{issue_id}/runs")
async def issue_task_runs(issue_id: str, limit: int = 50, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await _get_issue(db, issue_id)
    res = await db.execute(
        select(AgentTask)
        .where(AgentTask.issue_id == issue_id)
        .order_by(AgentTask.created_at.desc())
        .limit(min(limit, 200))
    )
    return [task_to_dict(t) for t in res.scalars()]


@tasks_router.post("/issues/{issue_id}/rerun", status_code=201)
async def rerun_issue(issue_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    """Re-enfileira a issue (RerunIssue do multica): marca rerun_of_task_id e
    reusa work_dir/sessão da execução anterior."""
    issue = await _get_issue(db, issue_id)
    res = await db.execute(
        select(AgentTask).where(AgentTask.issue_id == issue_id).order_by(AgentTask.created_at.desc()).limit(1)
    )
    prev = res.scalars().first()
    agent_id = issue.assignee_id if issue.assignee_type == "agent" else (prev.agent_id if prev else None)
    if not agent_id:
        raise HTTPException(422, "issue não tem agente atribuído nem execuções anteriores")
    agent = await _get_agent(db, agent_id)
    await agents_svc.ensure_can_invoke(db, user.id, agent)
    active = await db.execute(
        select(AgentTask.id).where(
            AgentTask.issue_id == issue_id, AgentTask.status.in_(agents_svc.ACTIVE_TASK_STATUSES)
        )
    )
    if active.first() is not None:
        raise HTTPException(409, "issue já tem task ativa")
    prompt = issue.title if not issue.description else f"{issue.title}\n\n{issue.description}"
    task = AgentTask(
        workspace_id=issue.workspace_id,
        agent_id=agent.id,
        issue_id=issue.id,
        kind="issue",
        status="queued",
        prompt=prompt,
        rerun_of_task_id=prev.id if prev else None,
        work_dir=prev.work_dir if prev else None,
        session_id=prev.session_id if prev else None,
    )
    db.add(task)
    await db.commit()
    await hub.publish(
        task.workspace_id,
        "task:queued",
        {"task_id": task.id, "agent_id": agent.id, "issue_id": issue.id, "kind": "issue", "rerun": True},
    )
    return task_to_dict(task)


@tasks_router.get("/{task_id}")
async def get_task(task_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    res = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    task = res.scalars().first()
    if task is None:
        raise HTTPException(404, "task não encontrada")
    return task_to_dict(task)


@tasks_router.get("/{task_id}/messages")
async def task_messages(
    task_id: str,
    after_seq: int | None = None,
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = select(TaskMessage).where(TaskMessage.task_id == task_id)
    if after_seq is not None:
        stmt = stmt.where(TaskMessage.seq > after_seq)
    stmt = stmt.order_by(TaskMessage.seq, TaskMessage.created_at).limit(min(limit, 1000))
    res = await db.execute(stmt)
    return [
        {
            "id": m.id,
            "seq": m.seq,
            "role": m.role,
            "type": m.type or m.role,
            "tool": m.tool,
            "content": m.content,
            "input": m.input,
            "output": m.output,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in res.scalars()
    ]


# ── Usage por task (multica ReportTaskUsage / task_usage) ─────────────
@tasks_router.get("/{task_id}/usage")
async def get_task_usage(task_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    rows = await agents_svc.task_usage_rows(db, task_id)
    return [agents_svc.usage_to_dict(u) for u in rows]


@tasks_router.post("/{task_id}/usage", status_code=201)
async def report_task_usage(
    task_id: str, payload: UsageIn, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    res = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    task = res.scalars().first()
    if task is None:
        raise HTTPException(404, "task não encontrada")
    row = await agents_svc.record_task_usage(
        db,
        task,
        provider=payload.provider,
        model=payload.model,
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        cache_read_tokens=payload.cache_read_tokens,
        cache_write_tokens=payload.cache_write_tokens,
        cost_usd=payload.cost_usd,
    )
    return agents_svc.usage_to_dict(row)


@tasks_router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    res = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    task = res.scalars().first()
    if task is None:
        raise HTTPException(404, "task não encontrada")
    agent = await db.get(Agent, task.agent_id)
    if agent is not None and not user.id.startswith("agent:"):
        can = await agents_svc.can_invoke_agent(db, user.id, agent) or await agents_svc.can_manage_agent(db, user.id, agent)
        if not can:
            raise HTTPException(403, "sem permissão para cancelar tasks deste agente")
    if task.status not in ("queued", "dispatched", "running"):
        raise HTTPException(409, f"task não pode ser cancelada no status {task.status}")
    # pedido de cancelamento: status vira cancelled JÁ; o runner observa
    # (watchdog), mata o subprocesso e faz o cancel-ack sem sobrescrever
    # (finalização dele é UPDATE ... WHERE status='running').
    task.status = "cancelled"
    task.cancel_requested = True
    task.finished_at = now()
    await db.commit()
    await hub.publish(task.workspace_id, "task:cancelled", {"task_id": task.id})
    # task de chat: finaliza na sessão (chat:done/chat:cancel_finalized +
    # draft restore quando a resposta ficou vazia — multica CancelTaskByUser)
    if task.kind == "chat" and task.chat_session_id:
        from ryu.services import chat as chat_service

        try:
            await chat_service.finalize_cancelled_chat_task(db, task)
        except Exception:
            pass  # best-effort: cancelamento já está persistido
    return task_to_dict(task)


# ── Página /w/{slug}/agents ───────────────────────────────────────────
async def _workspace_by_slug(db: AsyncSession, slug: str) -> Workspace:
    res = await db.execute(select(Workspace).where(Workspace.slug == slug))
    ws = res.scalars().first()
    if ws is None:
        raise HTTPException(404, "workspace não encontrado")
    return ws


@pages_router.get("/w/{slug}/agents", response_class=HTMLResponse)
async def agents_page(slug: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    ws = await _workspace_by_slug(db, slug)
    res = await db.execute(
        select(Agent).where(Agent.workspace_id == ws.id, Agent.archived_at.is_(None)).order_by(Agent.name)
    )
    agents = list(res.scalars())
    res = await db.execute(
        select(AgentTask).where(AgentTask.workspace_id == ws.id)
        .order_by(AgentTask.created_at.desc()).limit(20)
    )
    tasks = list(res.scalars())
    agent_names = {a.id: a.name for a in agents}
    return templates.TemplateResponse(
        "agents/index.html",
        {
            "request": request,
            "user": user,
            "workspace": ws,
            "active_nav": "agents",
            "agents": agents,
            "tasks": tasks,
            "agent_names": agent_names,
        },
    )


@pages_router.post("/w/{slug}/agents")
async def agents_page_create(
    slug: str,
    name: str = Form(...),
    handle: str = Form(""),
    description: str = Form(""),
    runtime: str = Form("claude"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    h = (handle or name).strip().lstrip("@").lower().replace(" ", "-")
    agent = Agent(
        workspace_id=ws.id,
        name=name.strip(),
        handle=h,
        description=description,
        runtime=runtime,
        created_by=None if user.id.startswith("agent:") else user.id,
    )
    db.add(agent)
    await db.commit()
    await hub.publish(ws.id, "agent:status", {"agent_id": agent.id, "status": agent.status})
    return RedirectResponse(f"/w/{slug}/agents", status_code=303)
