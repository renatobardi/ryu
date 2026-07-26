"""API do domínio DAEMON-CLI: execução externa de tasks + handoff do CLI.

Routers (montados no main.py):
- `router`          prefix="/api/daemon"   — register/deregister/heartbeat,
  claim/lease/report do protocolo de execução, requests de update/model-list,
  WS de wakeup (GET /api/daemon/ws). Auth: rdt_ (workspace-scoped) OU PAT/JWT
  com checagem de membership (multica middleware DaemonAuth).
- `runtimes_router` prefix="/api/runtimes" — listagem p/ UI + initiate/poll de
  update remoto e model-list (multica runtime_update.go / runtime_models.go).
- `cli_router`      prefix="/api"          — POST /api/cli-token (handoff do
  login por browser, multica IssueCliToken) e members do workspace p/ o CLI.
- `pages_router`    sem prefixo            — GET /cli-login (página do fluxo
  de login do CLI).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.config import settings
from ryu.db import SessionLocal, get_db
from ryu.models import (
    Agent,
    AgentRuntime,
    AgentTask,
    ApiToken,
    Member,
    RuntimeProfile,
    TaskMessage,
    User,
    Workspace,
    now,
)
from ryu.realtime.hub import hub
from ryu.services import daemon as svc
from ryu.services.auth import create_pat, current_user, decode_jwt, resolve_token
from ryu.services.daemon import DaemonError, daemon_hub

log = structlog.get_logger("ryu.api.daemon")

router = APIRouter()
runtimes_router = APIRouter()
cli_router = APIRouter()
pages_router = APIRouter()

# instala o wakeup de task:queued → daemon:task_available no WS
svc.install_task_wakeup()


def _err(e: DaemonError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=e.message)


# ── DaemonAuth (rdt_ workspace-scoped OU PAT/JWT + membership) ────────
@dataclass
class DaemonIdentity:
    kind: str  # daemon|pat|jwt
    user_id: str | None = None
    workspace_id: str | None = None  # escopo do rdt_
    daemon_id: str | None = None

    async def can_access(self, db: AsyncSession, workspace_id: str) -> bool:
        if self.kind == "daemon":
            return self.workspace_id == workspace_id
        if self.user_id:
            res = await db.execute(
                select(Member).where(
                    Member.workspace_id == workspace_id, Member.user_id == self.user_id
                )
            )
            return res.scalars().first() is not None
        return False


async def _identity_from_token(db: AsyncSession, raw: str) -> DaemonIdentity | None:
    tok = await resolve_token(db, raw)
    if tok is not None:
        if tok.kind == "daemon":
            return DaemonIdentity(
                kind="daemon",
                user_id=tok.user_id,
                workspace_id=tok.workspace_id,
                daemon_id=svc.token_daemon_id(tok),
            )
        if tok.kind == "pat":
            return DaemonIdentity(kind="pat", user_id=tok.user_id)
        return None  # rat_ não autoriza endpoints de daemon
    user_id = decode_jwt(raw)
    if user_id:
        return DaemonIdentity(kind="jwt", user_id=user_id)
    return None


async def daemon_identity(request: Request, db: AsyncSession = Depends(get_db)) -> DaemonIdentity:
    authz = request.headers.get("Authorization", "")
    if authz.lower().startswith("bearer "):
        ident = await _identity_from_token(db, authz[7:].strip())
        if ident is not None:
            return ident
        raise HTTPException(401, "token inválido para a API de daemon")
    # cookie JWT (browser/dev)
    from ryu.services.auth import AUTH_COOKIE

    cookie = request.cookies.get(AUTH_COOKIE)
    if cookie:
        user_id = decode_jwt(cookie)
        if user_id:
            return DaemonIdentity(kind="jwt", user_id=user_id)
    raise HTTPException(401, "Não autenticado")


async def _require_ws(db: AsyncSession, ident: DaemonIdentity, workspace_id: str) -> None:
    if not await ident.can_access(db, workspace_id):
        raise HTTPException(403, "sem acesso a este workspace")


async def _runtime_for(db: AsyncSession, ident: DaemonIdentity, runtime_id: str) -> AgentRuntime:
    try:
        rt = await svc.get_runtime(db, runtime_id)
    except DaemonError as e:
        raise _err(e)
    await _require_ws(db, ident, rt.workspace_id)
    return rt


async def _task_for(db: AsyncSession, ident: DaemonIdentity, task_id: str) -> AgentTask:
    task = await db.get(AgentTask, task_id)
    if task is None:
        raise HTTPException(404, "task não encontrada")
    await _require_ws(db, ident, task.workspace_id)
    return task


# ── Schemas ───────────────────────────────────────────────────────────
class RuntimeIn(BaseModel):
    provider: str
    version: str = ""
    name: str = ""


class RegisterIn(BaseModel):
    workspace_id: str | None = None
    daemon_id: str
    device_name: str = ""
    device_info: str = ""
    runtimes: list[RuntimeIn] = []
    issue_token: bool = True  # emite rdt_ quando autenticado por PAT/JWT


class DeregisterIn(BaseModel):
    workspace_id: str | None = None
    daemon_id: str | None = None
    runtime_ids: list[str] = []


class HeartbeatIn(BaseModel):
    runtime_id: str


class ClaimIn(BaseModel):
    runtime_id: str | None = None
    runtime_ids: list[str] = []
    max_tasks: int = 1


class StartIn(BaseModel):
    pass


class ProgressIn(BaseModel):
    message: str = ""
    lease_minutes: int | None = None


class MessageIn(BaseModel):
    role: str = "stdout"
    type: str = ""
    content: str = ""
    tool: str = ""
    input: dict | None = None
    output: dict | None = None


class MessagesIn(BaseModel):
    messages: list[MessageIn]


class CompleteIn(BaseModel):
    result_summary: str = ""
    session_id: str | None = None


class FailIn(BaseModel):
    error: str = ""
    failure_reason: str = "crash"


class UsageIn(BaseModel):
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0


class SessionIn(BaseModel):
    session_id: str


class UpdateResultIn(BaseModel):
    status: str = "completed"  # completed|failed
    message: str = ""
    version: str = ""


class ModelListResultIn(BaseModel):
    models: list = []
    error: str = ""


class TokenIssueIn(BaseModel):
    workspace_id: str
    daemon_id: str = "cli"


class InitiateUpdateIn(BaseModel):
    target_version: str = ""


# ── Serialização de task p/ o daemon (payload de execução) ────────────
async def _claimed_task_payload(db: AsyncSession, task: AgentTask) -> dict:
    from ryu.api.agents import task_to_dict

    d = task_to_dict(task)
    agent = await db.get(Agent, task.agent_id)
    if agent is not None:
        profile = None
        if getattr(agent, "profile_id", None):
            p = await db.get(RuntimeProfile, agent.profile_id)
            if p is not None:
                profile = {
                    "protocol_family": p.protocol_family,
                    "command_name": p.command_name,
                    "fixed_args": list(p.fixed_args or []),
                }
        d["agent"] = {
            "id": agent.id,
            "name": agent.name,
            "handle": agent.handle,
            "runtime": agent.runtime,
            "runtime_config": agent.runtime_config or {},
            "model": agent.model,
            "instructions": agent.instructions,
            "thinking_level": agent.thinking_level,
            "service_tier": agent.service_tier,
            "profile": profile,
        }
    return d


# ── Register / Deregister / Heartbeat ─────────────────────────────────
@router.post("/register")
async def daemon_register(
    payload: RegisterIn,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    workspace_id = payload.workspace_id or ident.workspace_id
    if not workspace_id:
        raise HTTPException(422, "workspace_id é obrigatório")
    await _require_ws(db, ident, workspace_id)
    daemon_id = payload.daemon_id.strip() or "daemon"
    runtimes = []
    for r in payload.runtimes:
        rt = await svc.upsert_runtime(
            db,
            workspace_id,
            daemon_id,
            r.provider,
            name=r.name,
            device_name=payload.device_name,
            version=r.version,
            device_info=payload.device_info,
        )
        runtimes.append(rt)
    await db.commit()
    for rt in runtimes:
        await db.refresh(rt)
    token_raw = None
    if payload.issue_token and ident.kind != "daemon":
        token_raw, _ = await svc.create_daemon_token(db, workspace_id, daemon_id, ident.user_id)
    await hub.publish(
        workspace_id,
        "runtime:registered",
        {"daemon_id": daemon_id, "runtimes": [svc.runtime_to_dict(rt) for rt in runtimes]},
    )
    return {
        "workspace_id": workspace_id,
        "daemon_id": daemon_id,
        "runtimes": [svc.runtime_to_dict(rt) for rt in runtimes],
        "daemon_token": token_raw,  # exibido/entregue uma única vez
    }


@router.post("/deregister")
async def daemon_deregister(
    payload: DeregisterIn,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    count = 0
    if payload.runtime_ids:
        for rid in payload.runtime_ids:
            rt = await db.get(AgentRuntime, rid)
            if rt is None or not await ident.can_access(db, rt.workspace_id):
                continue
            rt.status = "offline"
            count += 1
        await db.commit()
    else:
        workspace_id = payload.workspace_id or ident.workspace_id
        daemon_id = payload.daemon_id or ident.daemon_id
        if not workspace_id or not daemon_id:
            raise HTTPException(422, "workspace_id + daemon_id (ou runtime_ids) são obrigatórios")
        await _require_ws(db, ident, workspace_id)
        count = await svc.mark_daemon_offline(db, workspace_id, daemon_id)
    return {"ok": True, "deregistered": count}


async def _heartbeat_ack(db: AsyncSession, rt: AgentRuntime) -> dict:
    rt.last_seen_at = now()
    rt.status = "online"
    await db.commit()
    pending_update, pending_models = svc.pending_for_runtime(rt.id)
    # tasks na fila p/ o provider deste runtime (dica de claim)
    res = await db.execute(
        select(AgentTask.id)
        .join(Agent, Agent.id == AgentTask.agent_id)
        .where(
            AgentTask.workspace_id == rt.workspace_id,
            AgentTask.status == "queued",
            Agent.runtime == rt.provider,
        )
    )
    queued = len(res.all())
    ack = {
        "runtime_id": rt.id,
        "status": "ok",
        "server_capabilities": ["claim", "messages", "usage", "recover_orphans", "ws_wakeup"],
        "queued_tasks": queued,
    }
    if pending_update:
        ack["pending_update"] = {"id": pending_update.id, "target_version": pending_update.target_version}
    if pending_models:
        ack["pending_model_list"] = {"id": pending_models.id}
    return ack


@router.post("/heartbeat")
async def daemon_heartbeat(
    payload: HeartbeatIn,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    rt = await db.get(AgentRuntime, payload.runtime_id)
    if rt is None:
        # runtime removido server-side: daemon deve re-registrar (multica runtime_gone)
        return {"runtime_id": payload.runtime_id, "status": "runtime_gone", "runtime_gone": True}
    await _require_ws(db, ident, rt.workspace_id)
    return await _heartbeat_ack(db, rt)


@router.get("/workspaces")
async def daemon_workspaces(
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    wss = await svc.daemon_workspaces(db, user_id=ident.user_id, workspace_id=ident.workspace_id)
    return [{"id": w.id, "slug": w.slug, "name": w.name} for w in wss]


@router.get("/workspaces/{workspace_id}/runtime-profiles")
async def daemon_runtime_profiles(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    await _require_ws(db, ident, workspace_id)
    res = await db.execute(
        select(RuntimeProfile).where(RuntimeProfile.workspace_id == workspace_id)
    )
    return [
        {
            "id": p.id,
            "display_name": p.display_name,
            "protocol_family": p.protocol_family,
            "command_name": p.command_name,
            "fixed_args": list(p.fixed_args or []),
        }
        for p in res.scalars()
    ]


# ── Tokens rdt_ (emissão dedicada + revogação) ────────────────────────
@router.post("/token", status_code=201)
async def issue_daemon_token(
    payload: TokenIssueIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.id.startswith("agent:"):
        raise HTTPException(403, "apenas usuários podem emitir tokens de daemon")
    res = await db.execute(
        select(Member).where(Member.workspace_id == payload.workspace_id, Member.user_id == user.id)
    )
    if res.scalars().first() is None:
        raise HTTPException(403, "sem acesso a este workspace")
    raw, row = await svc.create_daemon_token(db, payload.workspace_id, payload.daemon_id, user.id)
    return {
        "id": row.id,
        "token": raw,
        "workspace_id": row.workspace_id,
        "daemon_id": payload.daemon_id,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }


@router.get("/tokens")
async def list_daemon_tokens(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    res = await db.execute(
        select(Member).where(Member.workspace_id == workspace_id, Member.user_id == user.id)
    )
    if res.scalars().first() is None:
        raise HTTPException(403, "sem acesso a este workspace")
    rows = await svc.list_daemon_tokens(db, workspace_id)
    return [
        {
            "id": t.id,
            "daemon_id": svc.token_daemon_id(t),
            "workspace_id": t.workspace_id,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "expires_at": t.expires_at.isoformat() if t.expires_at else None,
        }
        for t in rows
    ]


@router.delete("/tokens/{token_id}")
async def revoke_daemon_token(
    token_id: str,
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    res = await db.execute(
        select(Member).where(Member.workspace_id == workspace_id, Member.user_id == user.id)
    )
    if res.scalars().first() is None:
        raise HTTPException(403, "sem acesso a este workspace")
    if not await svc.revoke_daemon_token(db, token_id, workspace_id):
        raise HTTPException(404, "token não encontrado")
    return {"ok": True}


# ── Claim / pending / recover ─────────────────────────────────────────
@router.post("/tasks/claim")
async def claim_tasks(
    payload: ClaimIn,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    runtime_ids = payload.runtime_ids or ([payload.runtime_id] if payload.runtime_id else [])
    if not runtime_ids:
        raise HTTPException(422, "runtime_id(s) é obrigatório")
    claimed: list[dict] = []
    remaining = max(1, payload.max_tasks)
    for rid in runtime_ids:
        if remaining <= 0:
            break
        rt = await _runtime_for(db, ident, rid)
        tasks = await svc.claim_tasks_for_runtime(db, rt, remaining)
        remaining -= len(tasks)
        for t in tasks:
            claimed.append(await _claimed_task_payload(db, t))
    return {"tasks": claimed}


@router.post("/runtimes/{runtime_id}/tasks/claim")
async def claim_tasks_by_runtime(
    runtime_id: str,
    payload: ClaimIn | None = None,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    rt = await _runtime_for(db, ident, runtime_id)
    tasks = await svc.claim_tasks_for_runtime(db, rt, (payload.max_tasks if payload else 1))
    return {"tasks": [await _claimed_task_payload(db, t) for t in tasks]}


@router.get("/runtimes/{runtime_id}/tasks/pending")
async def pending_tasks(
    runtime_id: str,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    rt = await _runtime_for(db, ident, runtime_id)
    res = await db.execute(
        select(AgentTask)
        .join(Agent, Agent.id == AgentTask.agent_id)
        .where(
            AgentTask.workspace_id == rt.workspace_id,
            AgentTask.status == "queued",
            Agent.runtime == rt.provider,
        )
        .order_by(AgentTask.created_at)
        .limit(50)
    )
    from ryu.api.agents import task_to_dict

    return {"tasks": [task_to_dict(t) for t in res.scalars()]}


@router.post("/runtimes/{runtime_id}/recover-orphans")
async def recover_orphans(
    runtime_id: str,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    rt = await _runtime_for(db, ident, runtime_id)
    recovered = await svc.recover_orphaned_tasks(db, rt)
    return {"recovered": recovered}


# ── Ciclo de vida da task (daemon-auth) ───────────────────────────────
@router.get("/tasks/{task_id}/status")
async def task_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    task = await _task_for(db, ident, task_id)
    return {"task_id": task.id, "status": task.status, "cancel_requested": task.cancel_requested}


@router.post("/tasks/{task_id}/start")
async def start_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    task = await _task_for(db, ident, task_id)
    res = await db.execute(
        sql_update(AgentTask)
        .where(AgentTask.id == task.id, AgentTask.status == "dispatched")
        .values(
            status="running",
            started_at=now(),
            last_heartbeat_at=now(),
            lease_expires_at=now() + timedelta(minutes=settings.task_lease_minutes),
        )
    )
    await db.commit()
    if (res.rowcount or 0) == 0:
        await db.refresh(task)
        raise HTTPException(409, f"task não está dispatched (status={task.status})")
    agent = await db.get(Agent, task.agent_id)
    if agent is not None and agent.status != "working":
        agent.status = "working"
        await db.commit()
        await hub.publish(task.workspace_id, "agent:status", {"agent_id": agent.id, "status": "working"})
    await hub.publish(task.workspace_id, "task:running", {"task_id": task.id, "agent_id": task.agent_id})
    return {"ok": True, "status": "running"}


@router.post("/tasks/{task_id}/progress")
async def report_progress(
    task_id: str,
    payload: ProgressIn,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    task = await _task_for(db, ident, task_id)
    if task.status not in ("dispatched", "running"):
        return {"ok": False, "status": task.status, "cancel_requested": task.cancel_requested}
    await svc.extend_lease(db, task, payload.lease_minutes)
    if payload.message:
        await hub.publish(
            task.workspace_id, "task:progress", {"task_id": task.id, "line": payload.message[:500]}
        )
    return {"ok": True, "status": task.status, "cancel_requested": task.cancel_requested}


@router.post("/tasks/{task_id}/messages", status_code=201)
async def report_messages(
    task_id: str,
    payload: MessagesIn,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    task = await _task_for(db, ident, task_id)
    res = await db.execute(select(TaskMessage.seq).where(TaskMessage.task_id == task.id))
    seq = max([v or 0 for (v,) in res.all()] or [0])
    added = 0
    for m in payload.messages[:200]:
        seq += 1
        db.add(
            TaskMessage(
                task_id=task.id,
                role=m.role or "stdout",
                content=(m.content or "")[:8000],
                seq=seq,
                type=m.type or m.role or "stdout",
                tool=m.tool or "",
                input=m.input,
                output=m.output,
            )
        )
        added += 1
    await db.commit()
    if added:
        last = payload.messages[min(added, len(payload.messages)) - 1]
        await hub.publish(
            task.workspace_id,
            "task:progress",
            {"task_id": task.id, "seq": seq, "type": last.type or last.role, "line": (last.content or "")[:500]},
        )
    return {"ok": True, "added": added, "last_seq": seq}


@router.get("/tasks/{task_id}/messages")
async def daemon_task_messages(
    task_id: str,
    after_seq: int | None = None,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    task = await _task_for(db, ident, task_id)
    stmt = select(TaskMessage).where(TaskMessage.task_id == task.id)
    if after_seq is not None:
        stmt = stmt.where(TaskMessage.seq > after_seq)
    stmt = stmt.order_by(TaskMessage.seq, TaskMessage.created_at).limit(1000)
    res = await db.execute(stmt)
    return [
        {"seq": m.seq, "role": m.role, "type": m.type, "tool": m.tool, "content": m.content}
        for m in res.scalars()
    ]


async def _finish_side_effects(task: AgentTask) -> None:
    """Efeitos pós-terminal fora da sessão do request (comenta issue, chat cb)."""
    from ryu.runner.loop import _finish_issue_task, _recompute_agent_status
    from ryu.services.chat import handle_chat_task_done

    async with SessionLocal() as db:
        agent = await db.get(Agent, task.agent_id)
        fresh = await db.get(AgentTask, task.id)
        if fresh is None:
            return
        if fresh.status == "completed" and fresh.kind == "issue" and agent is not None:
            await _finish_issue_task(db, fresh, agent)
        await _recompute_agent_status(db, task.agent_id, error=(fresh.status == "failed"))
    if task.kind == "chat":
        try:
            await handle_chat_task_done(task)
        except Exception:
            log.exception("daemon_chat_callback_failed", task_id=task.id)


@router.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: str,
    payload: CompleteIn,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    task = await _task_for(db, ident, task_id)
    res = await db.execute(
        sql_update(AgentTask)
        .where(AgentTask.id == task.id, AgentTask.status.in_(("dispatched", "running")))
        .values(
            status="completed",
            result_summary=(payload.result_summary or "")[:16000],
            error="",
            finished_at=now(),
            session_id=payload.session_id or task.session_id,
            lease_expires_at=None,
        )
    )
    await db.commit()
    if (res.rowcount or 0) == 0:
        await db.refresh(task)
        return {"ok": False, "status": task.status}  # cancelada por fora — preserva
    await db.refresh(task)
    await _finish_side_effects(task)
    await hub.publish(
        task.workspace_id,
        "task:completed",
        {"task_id": task.id, "agent_id": task.agent_id, "kind": task.kind,
         "issue_id": task.issue_id, "result_summary": task.result_summary},
    )
    return {"ok": True, "status": "completed"}


@router.post("/tasks/{task_id}/fail")
async def fail_task(
    task_id: str,
    payload: FailIn,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    task = await _task_for(db, ident, task_id)
    reason = payload.failure_reason or "crash"
    attempt = task.attempt or 1
    max_attempts = task.max_attempts or settings.task_default_max_attempts
    retryable = reason in svc.RETRYABLE_REASONS and attempt < max_attempts
    if retryable:
        res = await db.execute(
            sql_update(AgentTask)
            .where(AgentTask.id == task.id, AgentTask.status.in_(("dispatched", "running")))
            .values(
                status="queued",
                attempt=attempt + 1,
                failure_reason=reason,
                error=(payload.error or "")[:2000],
                lease_expires_at=None,
                started_at=None,
                last_heartbeat_at=None,
                runtime_id=None,
            )
        )
        await db.commit()
        if (res.rowcount or 0) == 0:
            await db.refresh(task)
            return {"ok": False, "status": task.status}
        await hub.publish(
            task.workspace_id, "task:queued", {"task_id": task.id, "retry": True, "attempt": attempt + 1}
        )
        return {"ok": True, "status": "queued", "attempt": attempt + 1}
    res = await db.execute(
        sql_update(AgentTask)
        .where(AgentTask.id == task.id, AgentTask.status.in_(("dispatched", "running")))
        .values(
            status="failed",
            failure_reason=reason,
            error=(payload.error or "")[:2000],
            finished_at=now(),
            lease_expires_at=None,
        )
    )
    await db.commit()
    if (res.rowcount or 0) == 0:
        await db.refresh(task)
        return {"ok": False, "status": task.status}
    await db.refresh(task)
    await _finish_side_effects(task)
    await hub.publish(
        task.workspace_id, "task:failed",
        {"task_id": task.id, "error": task.error, "failure_reason": reason},
    )
    return {"ok": True, "status": "failed"}


@router.post("/tasks/{task_id}/usage", status_code=201)
async def report_usage(
    task_id: str,
    payload: UsageIn,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    from ryu.services import agents as agents_svc

    task = await _task_for(db, ident, task_id)
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


@router.post("/tasks/{task_id}/cancel-ack")
async def cancel_ack(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    task = await _task_for(db, ident, task_id)
    await db.execute(
        sql_update(AgentTask)
        .where(AgentTask.id == task.id, AgentTask.status.in_(("dispatched", "running")))
        .values(status="cancelled", cancel_requested=True, finished_at=now())
    )
    await db.commit()
    await db.refresh(task)
    from ryu.runner.loop import _recompute_agent_status

    async with SessionLocal() as sdb:
        await _recompute_agent_status(sdb, task.agent_id)
    await hub.publish(task.workspace_id, "task:cancelled", {"task_id": task.id, "ack": True})
    return {"ok": True, "status": task.status}


@router.post("/tasks/{task_id}/session")
async def pin_session(
    task_id: str,
    payload: SessionIn,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    task = await _task_for(db, ident, task_id)
    task.session_id = payload.session_id
    await db.commit()
    return {"ok": True}


# ── Report de update / model-list ─────────────────────────────────────
@router.post("/runtimes/{runtime_id}/update/{update_id}/result")
async def report_update_result(
    runtime_id: str,
    update_id: str,
    payload: UpdateResultIn,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    rt = await _runtime_for(db, ident, runtime_id)
    try:
        req = svc.report_update_result(update_id, payload.status, payload.message, payload.version)
    except DaemonError as e:
        raise _err(e)
    if payload.version:
        rt.version = payload.version
        await db.commit()
    await hub.publish(rt.workspace_id, "runtime:update_done", req.to_dict())
    return req.to_dict()


@router.post("/runtimes/{runtime_id}/models/{request_id}/result")
async def report_models_result(
    runtime_id: str,
    request_id: str,
    payload: ModelListResultIn,
    db: AsyncSession = Depends(get_db),
    ident: DaemonIdentity = Depends(daemon_identity),
):
    rt = await _runtime_for(db, ident, runtime_id)
    try:
        req = svc.report_model_list_result(request_id, payload.models, payload.error)
    except DaemonError as e:
        raise _err(e)
    await hub.publish(rt.workspace_id, "runtime:models_done", req.to_dict())
    return req.to_dict()


# ── WebSocket do daemon (wakeup + heartbeat/RPC) ──────────────────────
@router.websocket("/ws")
async def daemon_ws(websocket: WebSocket):
    import json as _json

    token = websocket.query_params.get("token", "")
    if not token:
        authz = websocket.headers.get("Authorization", "")
        if authz.lower().startswith("bearer "):
            token = authz[7:].strip()
    async with SessionLocal() as db:
        ident = await _identity_from_token(db, token) if token else None
        if ident is None:
            await websocket.close(code=4401)
            return
        wss = await svc.daemon_workspaces(db, user_id=ident.user_id, workspace_id=ident.workspace_id)
        workspace_ids = [w.id for w in wss]
    await websocket.accept()
    daemon_hub.register(workspace_ids, websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = _json.loads(raw)
            except ValueError:
                continue
            mtype = msg.get("type")
            payload = msg.get("payload") or {}
            req_id = msg.get("id")
            if mtype == "ping":
                await websocket.send_text(_json.dumps({"type": "pong", "id": req_id}))
            elif mtype == "daemon:heartbeat":
                async with SessionLocal() as db:
                    rt = await db.get(AgentRuntime, payload.get("runtime_id", ""))
                    if rt is None or not await ident.can_access(db, rt.workspace_id):
                        ack = {
                            "runtime_id": payload.get("runtime_id"),
                            "status": "runtime_gone",
                            "runtime_gone": True,
                        }
                    else:
                        ack = await _heartbeat_ack(db, rt)
                await websocket.send_text(
                    _json.dumps({"type": "daemon:heartbeat_ack", "id": req_id, "payload": ack})
                )
            elif mtype == "daemon:workspaces":
                async with SessionLocal() as db:
                    wss = await svc.daemon_workspaces(
                        db, user_id=ident.user_id, workspace_id=ident.workspace_id
                    )
                await websocket.send_text(
                    _json.dumps(
                        {
                            "type": "daemon:workspaces_changed",
                            "id": req_id,
                            "payload": {"workspaces": [{"id": w.id, "slug": w.slug, "name": w.name} for w in wss]},
                        }
                    )
                )
            elif mtype == "daemon:runtime_profiles":
                wsid = payload.get("workspace_id", "")
                async with SessionLocal() as db:
                    ok = await ident.can_access(db, wsid)
                    profiles = []
                    if ok:
                        res = await db.execute(
                            select(RuntimeProfile).where(RuntimeProfile.workspace_id == wsid)
                        )
                        profiles = [
                            {
                                "id": p.id,
                                "display_name": p.display_name,
                                "protocol_family": p.protocol_family,
                                "command_name": p.command_name,
                                "fixed_args": list(p.fixed_args or []),
                            }
                            for p in res.scalars()
                        ]
                await websocket.send_text(
                    _json.dumps(
                        {
                            "type": "daemon:runtime_profiles_changed",
                            "id": req_id,
                            "payload": {"workspace_id": wsid, "profiles": profiles},
                        }
                    )
                )
            elif mtype == "daemon:rpc_request":
                # RPC de claim via WS (multica daemon:rpc_request)
                method = payload.get("method")
                result: dict = {}
                if method == "claim":
                    async with SessionLocal() as db:
                        rt = await db.get(AgentRuntime, payload.get("runtime_id", ""))
                        tasks = []
                        if rt is not None and await ident.can_access(db, rt.workspace_id):
                            claimed = await svc.claim_tasks_for_runtime(
                                db, rt, int(payload.get("max_tasks") or 1)
                            )
                            tasks = [await _claimed_task_payload(db, t) for t in claimed]
                        result = {"tasks": tasks}
                await websocket.send_text(
                    _json.dumps({"type": "daemon:rpc_response", "id": req_id, "payload": result}, default=str)
                )
    except WebSocketDisconnect:
        pass
    except Exception:
        log.warning("daemon_ws_error")
    finally:
        daemon_hub.unregister(websocket)


# ── /api/runtimes (UI/API user-auth) ──────────────────────────────────
async def _member_runtime(db: AsyncSession, user: User, runtime_id: str) -> AgentRuntime:
    rt = await db.get(AgentRuntime, runtime_id)
    if rt is None:
        raise HTTPException(404, "runtime não encontrado")
    if not user.id.startswith("agent:"):
        res = await db.execute(
            select(Member).where(Member.workspace_id == rt.workspace_id, Member.user_id == user.id)
        )
        if res.scalars().first() is None:
            raise HTTPException(403, "sem acesso a este workspace")
    return rt


@runtimes_router.get("")
async def list_runtimes(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    rts = await svc.list_runtimes(db, workspace_id)
    return [svc.runtime_to_dict(rt) for rt in rts]


@runtimes_router.delete("/{runtime_id}", status_code=204)
async def delete_runtime(
    runtime_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    rt = await _member_runtime(db, user, runtime_id)
    await db.delete(rt)
    await db.commit()
    from fastapi.responses import Response

    return Response(status_code=204)


@runtimes_router.post("/{runtime_id}/update", status_code=202)
async def initiate_update(
    runtime_id: str,
    payload: InitiateUpdateIn | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    rt = await _member_runtime(db, user, runtime_id)
    req = svc.initiate_update(rt, payload.target_version if payload else "")
    return req.to_dict()


@runtimes_router.get("/{runtime_id}/update/{update_id}")
async def poll_update(
    runtime_id: str,
    update_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    await _member_runtime(db, user, runtime_id)
    req = svc.get_request(update_id)
    if req is None or req.kind != "update" or req.runtime_id != runtime_id:
        raise HTTPException(404, "update não encontrado")
    return req.to_dict()


@runtimes_router.post("/{runtime_id}/models", status_code=202)
async def initiate_models(
    runtime_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    rt = await _member_runtime(db, user, runtime_id)
    req = svc.initiate_model_list(rt)
    return req.to_dict()


@runtimes_router.get("/{runtime_id}/models/{request_id}")
async def poll_models(
    runtime_id: str,
    request_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    await _member_runtime(db, user, runtime_id)
    req = svc.get_request(request_id)
    if req is None or req.kind != "model_list" or req.runtime_id != runtime_id:
        raise HTTPException(404, "request não encontrada")
    return req.to_dict()


# ── CLI: token handoff + members ──────────────────────────────────────
@cli_router.post("/cli-token")
async def issue_cli_token(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    """Sessão autenticada por cookie emite um PAT p/ handoff ao CLI
    (multica IssueCliToken)."""
    if user.id.startswith("agent:"):
        raise HTTPException(403, "apenas usuários")
    raw, _ = await create_pat(db, user.id, name="cli")
    return {"token": raw}


@cli_router.get("/workspaces/{workspace_id}/members")
async def workspace_members(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    if not user.id.startswith("agent:"):
        res = await db.execute(
            select(Member).where(Member.workspace_id == workspace_id, Member.user_id == user.id)
        )
        if res.scalars().first() is None:
            raise HTTPException(403, "sem acesso a este workspace")
    res = await db.execute(
        select(Member, User)
        .join(User, User.id == Member.user_id)
        .where(Member.workspace_id == workspace_id)
        .order_by(Member.created_at)
    )
    return [
        {"id": m.id, "user_id": u.id, "email": u.email, "name": u.name, "role": m.role}
        for m, u in res.all()
    ]


@cli_router.get("/workspaces/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await db.get(Workspace, workspace_id)
    if ws is None:
        res = await db.execute(select(Workspace).where(Workspace.slug == workspace_id))
        ws = res.scalars().first()
    if ws is None:
        raise HTTPException(404, "workspace não encontrado")
    if not user.id.startswith("agent:"):
        res = await db.execute(
            select(Member).where(Member.workspace_id == ws.id, Member.user_id == user.id)
        )
        if res.scalars().first() is None:
            raise HTTPException(403, "sem acesso a este workspace")
    return {"id": ws.id, "slug": ws.slug, "name": ws.name, "issue_prefix": ws.issue_prefix}


# ── Página /cli-login (fluxo de login por browser do CLI) ─────────────
_CLI_LOGIN_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Ryu — CLI login</title>
<style>body{font-family:system-ui;background:#0d0e12;color:#e2e2e6;display:flex;
align-items:center;justify-content:center;height:100vh;margin:0}
.card{background:#17181d;border:1px solid #2a2b33;border-radius:12px;padding:32px;max-width:420px}
a{color:#8b5cf6}</style></head>
<body><div class="card"><h2>Autorizar o Ryu CLI</h2>
<p id="msg">Gerando token e devolvendo ao terminal…</p>
<script>
const redirect = new URLSearchParams(location.search).get('redirect_uri');
async function go(){
  try{
    const r = await fetch('/api/cli-token', {method:'POST'});
    if(r.status===401){
      document.getElementById('msg').innerHTML =
        'Você não está logado. <a href="/login">Faça login</a> e recarregue esta página.';
      return;
    }
    const data = await r.json();
    if(redirect){ location.href = redirect + (redirect.includes('?')?'&':'?') + 'token=' + encodeURIComponent(data.token); }
    else { document.getElementById('msg').textContent = 'Token: ' + data.token; }
  }catch(e){ document.getElementById('msg').textContent = 'Erro: ' + e; }
}
go();
</script></div></body></html>"""


@pages_router.get("/cli-login", response_class=HTMLResponse)
async def cli_login_page(request: Request):
    redirect_uri = request.query_params.get("redirect_uri", "")
    if redirect_uri:
        from urllib.parse import urlparse

        host = (urlparse(redirect_uri).hostname or "").lower()
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise HTTPException(400, "redirect_uri deve apontar para localhost")
    return HTMLResponse(_CLI_LOGIN_HTML)
