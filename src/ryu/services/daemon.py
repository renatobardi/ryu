"""Serviço do domínio DAEMON (execução externa de tasks) — daemon-cli ciclo 1.

Paridade multica:
- Tokens rdt_ workspace-scoped (multica 029_daemon_token / GenerateDaemonToken):
  emitidos no register (ou endpoint dedicado), com expiração e revogação.
- agent_runtime: upsert por (workspace, daemon_id, provider); online/offline
  derivado de last_seen_at (multica 004_agent_runtime_loop).
- Claim atômico queued→dispatched com lease + recover-orphans por runtime.
- Requests pendentes de update / model-list entregues via heartbeat-ack e
  reportadas pelo daemon (store em memória, single-node — multica
  runtime_update.go / runtime_models.go com Redis fica fora de escopo).
- DaemonHub: WS por workspace p/ wakeup `daemon:task_available` no enqueue
  (multica daemonws/hub.go NotifyTaskAvailable).
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.config import settings
from ryu.models import Agent, AgentRuntime, AgentTask, ApiToken, Issue, Member, Workspace
from ryu.realtime.hub import hub

log = structlog.get_logger("ryu.daemon")

RETRYABLE_REASONS = ("crash", "timeout", "lease_expired")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class DaemonError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ── Tokens rdt_ (workspace-scoped) ────────────────────────────────────
async def create_daemon_token(
    db: AsyncSession, workspace_id: str, daemon_id: str, user_id: str | None = None
) -> tuple[str, ApiToken]:
    """Emite um token rdt_ com escopo de workspace+daemon (multica 029)."""
    raw = "rdt_" + secrets.token_urlsafe(32)
    row = ApiToken(
        token_hash=_sha256(raw),
        kind="daemon",
        user_id=user_id,
        workspace_id=workspace_id,
        name=f"daemon:{daemon_id}",
        expires_at=_now() + timedelta(days=settings.daemon_token_ttl_days),
    )
    db.add(row)
    await db.commit()
    return raw, row


async def list_daemon_tokens(db: AsyncSession, workspace_id: str) -> list[ApiToken]:
    res = await db.execute(
        select(ApiToken)
        .where(
            ApiToken.kind == "daemon",
            ApiToken.workspace_id == workspace_id,
            ApiToken.revoked.is_(False),
        )
        .order_by(ApiToken.created_at.desc())
    )
    return list(res.scalars())


async def revoke_daemon_token(db: AsyncSession, token_id: str, workspace_id: str) -> bool:
    res = await db.execute(
        select(ApiToken).where(
            ApiToken.id == token_id, ApiToken.kind == "daemon", ApiToken.workspace_id == workspace_id
        )
    )
    tok = res.scalars().first()
    if tok is None:
        return False
    tok.revoked = True
    await db.commit()
    return True


def token_daemon_id(tok: ApiToken) -> str | None:
    if tok.name and tok.name.startswith("daemon:"):
        return tok.name.split(":", 1)[1]
    return None


# ── Runtimes (agent_runtime) ──────────────────────────────────────────
def runtime_to_dict(rt: AgentRuntime) -> dict:
    return {
        "id": rt.id,
        "workspace_id": rt.workspace_id,
        "daemon_id": rt.daemon_id,
        "name": rt.name,
        "device_name": rt.device_name,
        "runtime_mode": rt.runtime_mode,
        "provider": rt.provider,
        "version": rt.version,
        "status": effective_runtime_status(rt),
        "device_info": rt.device_info,
        "metadata": rt.meta or {},
        "last_seen_at": rt.last_seen_at.isoformat() if rt.last_seen_at else None,
        "created_at": rt.created_at.isoformat() if rt.created_at else None,
    }


def effective_runtime_status(rt: AgentRuntime) -> str:
    """Online/offline derivado de last_seen_at (não confia no campo status)."""
    seen = _aware(rt.last_seen_at)
    if seen is None or rt.status == "offline":
        return "offline"
    if (_now() - seen).total_seconds() > settings.runtime_offline_seconds:
        return "offline"
    return "online"


async def upsert_runtime(
    db: AsyncSession,
    workspace_id: str,
    daemon_id: str,
    provider: str,
    *,
    name: str = "",
    device_name: str = "",
    version: str = "",
    device_info: str = "",
    metadata: dict | None = None,
) -> AgentRuntime:
    res = await db.execute(
        select(AgentRuntime).where(
            AgentRuntime.workspace_id == workspace_id,
            AgentRuntime.daemon_id == daemon_id,
            AgentRuntime.provider == provider,
        )
    )
    rt = res.scalars().first()
    if rt is None:
        rt = AgentRuntime(workspace_id=workspace_id, daemon_id=daemon_id, provider=provider)
        db.add(rt)
    rt.name = name or rt.name or f"{provider} @ {device_name or daemon_id}"
    rt.device_name = device_name or rt.device_name
    rt.version = version or rt.version
    rt.device_info = device_info or rt.device_info
    if metadata is not None:
        rt.meta = metadata
    rt.status = "online"
    rt.last_seen_at = _now()
    await db.flush()
    return rt


async def get_runtime(db: AsyncSession, runtime_id: str) -> AgentRuntime:
    rt = await db.get(AgentRuntime, runtime_id)
    if rt is None:
        raise DaemonError("runtime não encontrado", 404)
    return rt


async def list_runtimes(db: AsyncSession, workspace_id: str) -> list[AgentRuntime]:
    res = await db.execute(
        select(AgentRuntime)
        .where(AgentRuntime.workspace_id == workspace_id)
        .order_by(AgentRuntime.created_at)
    )
    return list(res.scalars())


async def mark_daemon_offline(db: AsyncSession, workspace_id: str, daemon_id: str) -> int:
    res = await db.execute(
        sql_update(AgentRuntime)
        .where(AgentRuntime.workspace_id == workspace_id, AgentRuntime.daemon_id == daemon_id)
        .values(status="offline")
    )
    await db.commit()
    return res.rowcount or 0


async def online_providers(db: AsyncSession, workspace_id: str | None = None) -> set[tuple[str, str]]:
    """Pares (workspace_id, provider) com runtime externo online — usado pelo
    scheduler do servidor para acordar daemons quando há fila + runtime online."""
    stmt = select(AgentRuntime).where(AgentRuntime.status == "online")
    if workspace_id:
        stmt = stmt.where(AgentRuntime.workspace_id == workspace_id)
    res = await db.execute(stmt)
    pairs: set[tuple[str, str]] = set()
    for rt in res.scalars():
        if effective_runtime_status(rt) == "online":
            pairs.add((rt.workspace_id, rt.provider))
    return pairs


async def agent_is_online(db: AsyncSession, agent: Agent) -> bool:
    """Derivação online/offline do agente: só runtime externo do provider."""
    pairs = await online_providers(db, agent.workspace_id)
    return (agent.workspace_id, agent.runtime) in pairs


async def recompute_agent_status(db: AsyncSession, agent_id: str, *, error: bool = False) -> None:
    """Recalcula status do agente a partir de tasks ativas; publica no hub."""
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


async def finish_issue_task(db: AsyncSession, task: AgentTask, agent: Agent) -> None:
    """Comenta o resultado na issue e move para in_review."""
    if not task.issue_id:
        return
    res = await db.execute(select(Issue).where(Issue.id == task.issue_id))
    issue = res.scalars().first()
    if issue is None:
        return
    from ryu.services import issues as issues_svc

    try:
        await issues_svc.create_comment(db, issue.id, "agent", agent.id, task.result_summary)
    except Exception:
        log.warning("daemon_comment_failed", task_id=task.id)
    if issue.status in ("todo", "in_progress"):
        try:
            await issues_svc.update_issue(db, issue.id, "agent", agent.id, {"status": "in_review"})
        except Exception:
            log.warning("daemon_issue_move_failed", task_id=task.id)
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
            log.warning("daemon_notify_failed", task_id=task.id)


# ── Claim / lease (daemon-auth) ───────────────────────────────────────
async def claim_tasks_for_runtime(
    db: AsyncSession, runtime: AgentRuntime, max_tasks: int = 1
) -> list[AgentTask]:
    """Claim atômico: queued→dispatched com lease + runtime_id, respeitando
    max_concurrent_tasks por agente (multica ClaimTasksByRuntime)."""
    max_tasks = max(1, min(max_tasks, 20))
    res = await db.execute(
        select(AgentTask)
        .where(AgentTask.workspace_id == runtime.workspace_id, AgentTask.status == "queued")
        .order_by(AgentTask.created_at)
        .limit(100)
    )
    queued = list(res.scalars())
    if not queued:
        return []
    # contagem de ativos por agente
    res = await db.execute(
        select(AgentTask.agent_id).where(
            AgentTask.workspace_id == runtime.workspace_id,
            AgentTask.status.in_(("dispatched", "running")),
        )
    )
    counts: dict[str, int] = {}
    for (agid,) in res.all():
        counts[agid] = counts.get(agid, 0) + 1
    claimed: list[AgentTask] = []
    agents: dict[str, Agent | None] = {}
    for t in queued:
        if len(claimed) >= max_tasks:
            break
        if t.agent_id not in agents:
            agents[t.agent_id] = await db.get(Agent, t.agent_id)
        agent = agents[t.agent_id]
        if agent is None or getattr(agent, "archived_at", None):
            continue  # sweeper/loop interno finaliza
        if agent.runtime != runtime.provider:
            continue  # este runtime não executa esse provider
        limit = max(1, agent.max_concurrent_tasks or 1)
        if counts.get(t.agent_id, 0) >= limit:
            continue
        # claim guardado por status (atômico mesmo com runner in-process)
        upd = await db.execute(
            sql_update(AgentTask)
            .where(AgentTask.id == t.id, AgentTask.status == "queued")
            .values(
                status="dispatched",
                runtime_id=runtime.id,
                lease_expires_at=_now() + timedelta(minutes=settings.task_lease_minutes),
                last_heartbeat_at=_now(),
            )
        )
        if (upd.rowcount or 0) == 0:
            continue
        counts[t.agent_id] = counts.get(t.agent_id, 0) + 1
        claimed.append(t)
    await db.commit()
    for t in claimed:
        await db.refresh(t)
    return claimed


async def extend_lease(db: AsyncSession, task: AgentTask, minutes: int | None = None) -> None:
    task.lease_expires_at = _now() + timedelta(minutes=minutes or settings.task_lease_minutes)
    task.last_heartbeat_at = _now()
    await db.commit()


async def recover_orphaned_tasks(db: AsyncSession, runtime: AgentRuntime) -> list[dict]:
    """Pós-crash do daemon: tasks dispatched/running deste runtime com lease
    vencido voltam p/ queued (ou falham no limite de attempts)."""
    now = _now()
    res = await db.execute(
        select(AgentTask).where(
            AgentTask.runtime_id == runtime.id,
            AgentTask.status.in_(("dispatched", "running")),
        )
    )
    recovered: list[dict] = []
    for t in res.scalars():
        attempt = t.attempt or 1
        max_attempts = t.max_attempts or settings.task_default_max_attempts
        if not t.cancel_requested and attempt < max_attempts:
            t.status = "queued"
            t.attempt = attempt + 1
            t.failure_reason = "lease_expired"
            t.error = "daemon caiu durante a execução — task recuperada"
            t.lease_expires_at = None
            t.started_at = None
            t.last_heartbeat_at = None
            t.runtime_id = None
            recovered.append({"task_id": t.id, "status": "queued", "attempt": t.attempt})
        else:
            t.status = "cancelled" if t.cancel_requested else "failed"
            t.failure_reason = "lease_expired"
            t.finished_at = now
            recovered.append({"task_id": t.id, "status": t.status})
    await db.commit()
    return recovered


# ── Requests pendentes: update remoto + model-list (store em memória) ─
@dataclass
class PendingRequest:
    id: str
    kind: str  # update|model_list
    runtime_id: str
    workspace_id: str
    status: str = "pending"  # pending|delivered|completed|failed
    target_version: str = ""
    message: str = ""
    version: str = ""
    models: list = field(default_factory=list)
    created_at: datetime = field(default_factory=_now)

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "kind": self.kind,
            "runtime_id": self.runtime_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }
        if self.kind == "update":
            d.update({"target_version": self.target_version, "message": self.message, "version": self.version})
        else:
            d.update({"models": self.models, "message": self.message})
        return d


_requests: dict[str, PendingRequest] = {}


def _prune_requests() -> None:
    cutoff = _now() - timedelta(hours=6)
    for rid in [r.id for r in _requests.values() if r.created_at < cutoff]:
        _requests.pop(rid, None)


def initiate_update(runtime: AgentRuntime, target_version: str = "") -> PendingRequest:
    _prune_requests()
    req = PendingRequest(
        id=uuid.uuid4().hex, kind="update", runtime_id=runtime.id,
        workspace_id=runtime.workspace_id, target_version=target_version or "latest",
    )
    _requests[req.id] = req
    return req


def initiate_model_list(runtime: AgentRuntime) -> PendingRequest:
    _prune_requests()
    # reusa request pendente do mesmo runtime (dedupe)
    for r in _requests.values():
        if r.kind == "model_list" and r.runtime_id == runtime.id and r.status in ("pending", "delivered"):
            return r
    req = PendingRequest(
        id=uuid.uuid4().hex, kind="model_list", runtime_id=runtime.id, workspace_id=runtime.workspace_id
    )
    _requests[req.id] = req
    return req


def pending_for_runtime(runtime_id: str) -> tuple[PendingRequest | None, PendingRequest | None]:
    """Próximo update e model-list pendentes p/ o heartbeat-ack; marca delivered."""
    upd = mdl = None
    for r in sorted(_requests.values(), key=lambda r: r.created_at):
        if r.runtime_id != runtime_id or r.status != "pending":
            continue
        if r.kind == "update" and upd is None:
            upd = r
        elif r.kind == "model_list" and mdl is None:
            mdl = r
    if upd:
        upd.status = "delivered"
    if mdl:
        mdl.status = "delivered"
    return upd, mdl


def get_request(request_id: str) -> PendingRequest | None:
    return _requests.get(request_id)


def report_update_result(request_id: str, status: str, message: str = "", version: str = "") -> PendingRequest:
    req = _requests.get(request_id)
    if req is None or req.kind != "update":
        raise DaemonError("update request não encontrada", 404)
    req.status = "completed" if status in ("completed", "success", "ok") else "failed"
    req.message = message
    req.version = version
    return req


def report_model_list_result(request_id: str, models: list, error: str = "") -> PendingRequest:
    req = _requests.get(request_id)
    if req is None or req.kind != "model_list":
        raise DaemonError("model-list request não encontrada", 404)
    if error:
        req.status = "failed"
        req.message = error
    else:
        req.status = "completed"
        req.models = models
    return req


# ── DaemonHub (WS wakeup) ─────────────────────────────────────────────
class DaemonHub:
    """Conexões WS de daemons, por workspace. Push de daemon:task_available
    no enqueue de task (latência ~0 em vez de esperar o poll)."""

    def __init__(self) -> None:
        self._conns: dict[str, set] = {}

    def register(self, workspace_ids: list[str], ws) -> None:
        for wid in workspace_ids:
            self._conns.setdefault(wid, set()).add(ws)

    def unregister(self, ws) -> None:
        for conns in self._conns.values():
            conns.discard(ws)

    async def notify(self, workspace_id: str, event: str, data: dict) -> None:
        import json

        msg = json.dumps({"type": event, "payload": data}, default=str)
        for ws in list(self._conns.get(workspace_id, ())):
            try:
                await ws.send_text(msg)
            except Exception:
                self.unregister(ws)

    async def notify_task_available(self, workspace_id: str, data: dict) -> None:
        await self.notify(workspace_id, "daemon:task_available", data)


daemon_hub = DaemonHub()

_wakeup_installed = False


def install_task_wakeup() -> None:
    """Intercepta hub.publish: todo `task:queued` também acorda os daemons
    conectados via WS (multica NotifyTaskAvailable no enqueue)."""
    global _wakeup_installed
    if _wakeup_installed:
        return
    _wakeup_installed = True
    orig_publish = hub.publish

    async def _publish(workspace_id: str, event: str, data: dict) -> None:
        await orig_publish(workspace_id, event, data)
        if event == "task:queued":
            try:
                await daemon_hub.notify_task_available(workspace_id, data)
            except Exception:
                log.warning("daemon_wakeup_failed", workspace_id=workspace_id)

    hub.publish = _publish  # type: ignore[method-assign]


# ── Workspaces visíveis pelo daemon ───────────────────────────────────
async def daemon_workspaces(
    db: AsyncSession, *, user_id: str | None, workspace_id: str | None
) -> list[Workspace]:
    """Watch list: token rdt_ → só o workspace do escopo; PAT/JWT → memberships."""
    if workspace_id:
        ws = await db.get(Workspace, workspace_id)
        return [ws] if ws else []
    if user_id:
        res = await db.execute(
            select(Workspace)
            .join(Member, Member.workspace_id == Workspace.id)
            .where(Member.user_id == user_id)
            .order_by(Workspace.created_at)
        )
        return list(res.scalars())
    return []
