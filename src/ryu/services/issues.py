"""Serviço do domínio ISSUES/TRACKER.

Regras centrais:
- key gerada via workspace.issue_counter (incremento atômico via UPDATE ... RETURNING quando possível).
- toda mutação grava ActivityLog e publica no hub.
- assignee polimórfico (member|agent); quando agent + status todo/in_progress → cria AgentTask queued.
"""
from __future__ import annotations

import json
import re
from typing import Any, Sequence

from sqlalchemy import case, delete, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.models import (
    ActivityLog,
    Agent,
    AgentTask,
    Comment,
    CommentReaction,
    Issue,
    IssueLabel,
    IssueReaction,
    IssueSubscriber,
    Label,
    Member,
    Project,
    User,
    Workspace,
    now,
)
from ryu.realtime.hub import hub

ISSUE_STATUSES = ["backlog", "todo", "in_progress", "in_review", "done", "blocked", "cancelled"]
PRIORITIES = ["urgent", "high", "medium", "low", "none"]
OPEN_STATUSES = ["backlog", "todo", "in_progress", "in_review", "blocked"]
SUBSCRIBER_REASONS = ["creator", "assignee", "commenter", "mentioned", "manual", "autopilot"]
SORT_FIELDS = ["created", "updated", "priority", "due_date", "position"]
GROUP_BY_FIELDS = ["status", "priority", "assignee", "project", "label"]

# metadata KV: contrato usado pelos agentes (paridade multica issue_metadata.go)
MAX_METADATA_KEYS = 50
MAX_METADATA_BYTES = 8192
METADATA_KEY_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.-]{0,63}$")

# @mentions em descrição/comentário
MENTION_RE = re.compile(r"@([A-Za-z0-9][A-Za-z0-9_.\-]*)")

# posições novas entram com esse passo no fim da coluna
POSITION_STEP = 1024.0


class IssueError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ── helpers ───────────────────────────────────────────────────────────
async def _log(
    db: AsyncSession,
    workspace_id: str,
    actor_type: str,
    actor_id: str,
    action: str,
    payload: dict,
    issue_id: str | None = None,
) -> None:
    db.add(
        ActivityLog(
            workspace_id=workspace_id,
            issue_id=issue_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            payload=payload,
        )
    )


def issue_to_dict(issue: Issue, labels: list[Label] | None = None) -> dict:
    d = {
        "id": issue.id,
        "workspace_id": issue.workspace_id,
        "key": issue.key,
        "title": issue.title,
        "description": issue.description,
        "status": issue.status,
        "priority": issue.priority,
        "assignee_type": issue.assignee_type,
        "assignee_id": issue.assignee_id,
        "creator_type": issue.creator_type,
        "creator_id": issue.creator_id,
        "parent_issue_id": issue.parent_issue_id,
        "project_id": issue.project_id,
        "position": issue.position,
        "due_date": issue.due_date.isoformat() if issue.due_date else None,
        "meta": issue.meta or {},
        "properties": issue.properties or {},
        "created_at": issue.created_at.isoformat() if issue.created_at else None,
        "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
    }
    if labels is not None:
        d["labels"] = [label_to_dict(lb) for lb in labels]
    return d


def label_to_dict(label: Label) -> dict:
    return {"id": label.id, "workspace_id": label.workspace_id, "name": label.name, "color": label.color}


def comment_to_dict(c: Comment, reactions: list[dict] | None = None) -> dict:
    d = {
        "id": c.id,
        "issue_id": c.issue_id,
        "author_type": c.author_type,
        "author_id": c.author_id,
        "body": c.body,
        "parent_comment_id": c.parent_comment_id,
        "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
        "resolved_by_type": c.resolved_by_type,
        "resolved_by_id": c.resolved_by_id,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
    if reactions is not None:
        d["reactions"] = reactions
    return d


async def get_workspace(db: AsyncSession, workspace_id: str) -> Workspace:
    ws = await db.get(Workspace, workspace_id)
    if ws is None:
        raise IssueError("workspace não encontrado", 404)
    return ws


async def get_issue(db: AsyncSession, issue_id: str) -> Issue:
    issue = await db.get(Issue, issue_id)
    if issue is None:
        raise IssueError("issue não encontrada", 404)
    return issue


async def _validate_squad(db: AsyncSession, workspace_id: str, squad_id: str) -> None:
    from ryu.models import Squad

    squad = await db.get(Squad, squad_id)
    if squad is None or squad.workspace_id != workspace_id:
        raise IssueError("squad não encontrada neste workspace", 404)


async def issue_labels(db: AsyncSession, issue_id: str) -> list[Label]:
    rows = await db.execute(
        select(Label).join(IssueLabel, IssueLabel.label_id == Label.id).where(IssueLabel.issue_id == issue_id)
    )
    return list(rows.scalars())


async def _next_key(db: AsyncSession, workspace_id: str) -> str:
    """Incrementa issue_counter e devolve a key. UPDATE atômico + reread."""
    await db.execute(
        update(Workspace)
        .where(Workspace.id == workspace_id)
        .values(issue_counter=Workspace.issue_counter + 1)
    )
    row = await db.execute(
        select(Workspace.issue_prefix, Workspace.issue_counter).where(Workspace.id == workspace_id)
    )
    prefix, counter = row.one()
    return f"{prefix}-{counter}"


async def _next_position(db: AsyncSession, workspace_id: str, status: str) -> float:
    row = await db.execute(
        select(Issue.position)
        .where(Issue.workspace_id == workspace_id, Issue.status == status)
        .order_by(Issue.position.desc())
        .limit(1)
    )
    maxpos = row.scalar_one_or_none()
    return (maxpos or 0.0) + POSITION_STEP


async def _maybe_enqueue_agent_task(db: AsyncSession, issue: Issue, actor_type: str, actor_id: str) -> AgentTask | None:
    """Se assignee é agent e status é todo/in_progress, cria AgentTask queued (sem duplicar).
    assignee_type='squad' → task de briefing do líder (mesmo trigger no assign e
    na promoção backlog→todo — multica enqueueSquadLeaderTask)."""
    if issue.assignee_type == "squad" and issue.assignee_id:
        from ryu.services import squads as squads_svc  # lazy: evita ciclo

        return await squads_svc.squad_briefing_on_assign(db, issue, actor_type, actor_id)
    if issue.assignee_type != "agent" or issue.assignee_id is None:
        return None
    if issue.status not in ("todo", "in_progress"):
        return None
    agent = await db.get(Agent, issue.assignee_id)
    if agent is None:
        return None
    if getattr(agent, "archived_at", None) is not None:
        raise IssueError("agente arquivado não pode receber tasks", 409)
    # canInvokeAgent (multica): membros só disparam agentes que podem invocar
    if actor_type == "member":
        from ryu.services import agents as agents_svc

        if not await agents_svc.can_invoke_agent(db, actor_id, agent):
            raise IssueError("sem permissão para invocar este agente", 403)
    existing = await db.execute(
        select(AgentTask.id).where(
            AgentTask.issue_id == issue.id,
            AgentTask.agent_id == agent.id,
            AgentTask.status.in_(["queued", "dispatched", "running"]),
        )
    )
    if existing.first() is not None:
        return None
    prompt = issue.title if not issue.description else f"{issue.title}\n\n{issue.description}"
    task = AgentTask(
        workspace_id=issue.workspace_id,
        agent_id=agent.id,
        issue_id=issue.id,
        kind="issue",
        status="queued",
        prompt=prompt,
    )
    db.add(task)
    await db.flush()
    await _log(
        db,
        issue.workspace_id,
        actor_type,
        actor_id,
        "task_queued",
        {"task_id": task.id, "agent_id": agent.id, "issue_key": issue.key},
        issue_id=issue.id,
    )
    return task


async def _publish_task_queued(task: AgentTask) -> None:
    await hub.publish(
        task.workspace_id,
        "task:queued",
        {"task_id": task.id, "agent_id": task.agent_id, "issue_id": task.issue_id, "kind": task.kind},
    )


# ── Subscribers (auto + manual) ───────────────────────────────────────
def subscriber_to_dict(s: IssueSubscriber) -> dict:
    return {
        "issue_id": s.issue_id,
        "user_type": s.user_type,
        "user_id": s.user_id,
        "reason": s.reason,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


async def list_subscribers(db: AsyncSession, issue_id: str) -> list[IssueSubscriber]:
    rows = await db.execute(
        select(IssueSubscriber).where(IssueSubscriber.issue_id == issue_id).order_by(IssueSubscriber.created_at)
    )
    return list(rows.scalars())


async def subscribe(
    db: AsyncSession, issue_id: str, user_type: str, user_id: str, reason: str = "manual"
) -> IssueSubscriber | None:
    """Insere subscriber se ainda não existe (idempotente). NÃO commita."""
    if user_type not in ("member", "agent") or not user_id:
        return None
    if reason not in SUBSCRIBER_REASONS:
        reason = "manual"
    existing = await db.execute(
        select(IssueSubscriber).where(
            IssueSubscriber.issue_id == issue_id,
            IssueSubscriber.user_type == user_type,
            IssueSubscriber.user_id == user_id,
        )
    )
    row = existing.scalars().first()
    if row is not None:
        return row
    sub = IssueSubscriber(issue_id=issue_id, user_type=user_type, user_id=user_id, reason=reason)
    db.add(sub)
    await db.flush()
    return sub


async def unsubscribe(db: AsyncSession, issue_id: str, user_type: str, user_id: str) -> None:
    await db.execute(
        delete(IssueSubscriber).where(
            IssueSubscriber.issue_id == issue_id,
            IssueSubscriber.user_type == user_type,
            IssueSubscriber.user_id == user_id,
        )
    )
    await db.commit()


async def resolve_mentions(db: AsyncSession, workspace_id: str, text: str) -> list[tuple[str, str]]:
    """Resolve @handles do texto → [(user_type, user_id)].

    Agents casam por handle; members por localpart do email ou nome (lower)."""
    if not text or "@" not in text:
        return []
    handles = {h.lower() for h in MENTION_RE.findall(text)}
    if not handles:
        return []
    out: list[tuple[str, str]] = []
    agents = (await db.execute(select(Agent).where(Agent.workspace_id == workspace_id))).scalars()
    for a in agents:
        if (a.handle or "").lstrip("@").lower() in handles:
            out.append(("agent", a.id))
    member_users = (
        await db.execute(
            select(User).join(Member, Member.user_id == User.id).where(Member.workspace_id == workspace_id)
        )
    ).scalars()
    for u in member_users:
        local = (u.email or "").split("@")[0].lower()
        if local in handles or (u.name or "").lower() in handles:
            out.append(("member", u.id))
    return out


async def _auto_subscribe_mentions(db: AsyncSession, issue: Issue, text: str) -> None:
    for utype, uid_ in await resolve_mentions(db, issue.workspace_id, text):
        await subscribe(db, issue.id, utype, uid_, "mentioned")


async def _notify_subscribers(
    db: AsyncSession,
    issue: Issue,
    actor_type: str,
    actor_id: str,
    title: str,
    body: str = "",
    severity: str = "info",
    group: str | None = "updates",
) -> None:
    """Fan-out p/ inbox dos subscribers (members; exclui o ator). Best-effort.

    `group` liga a notificação às notification preferences (muted suprime)."""
    from ryu.services import inbox as inbox_svc

    try:
        subs = await list_subscribers(db, issue.id)
        for s in subs:
            if s.user_type != "member":
                continue  # inbox é por usuário; agentes recebem via fila/task
            if s.user_type == actor_type and s.user_id == actor_id:
                continue
            await inbox_svc.notify(
                db, issue.workspace_id, s.user_id, severity, title, body,
                issue_id=issue.id, group=group,
            )
    except Exception:
        pass  # notificação nunca derruba a mutação principal


# ── Issues CRUD ───────────────────────────────────────────────────────
async def create_issue(
    db: AsyncSession,
    workspace_id: str,
    actor_type: str,
    actor_id: str,
    *,
    title: str,
    description: str = "",
    status: str = "backlog",
    priority: str = "none",
    assignee_type: str | None = None,
    assignee_id: str | None = None,
    parent_issue_id: str | None = None,
    project_id: str | None = None,
    label_ids: Sequence[str] | None = None,
) -> Issue:
    if not title.strip():
        raise IssueError("title é obrigatório")
    if status not in ISSUE_STATUSES:
        raise IssueError(f"status inválido: {status}")
    if priority not in PRIORITIES:
        raise IssueError(f"priority inválida: {priority}")
    if assignee_type not in (None, "member", "agent", "squad"):
        raise IssueError(f"assignee_type inválido: {assignee_type}")
    if (assignee_type is None) != (assignee_id is None):
        raise IssueError("assignee_type e assignee_id devem vir juntos")
    if assignee_type == "squad" and assignee_id:
        await _validate_squad(db, workspace_id, assignee_id)
    if parent_issue_id:
        parent = await get_issue(db, parent_issue_id)
        if parent.workspace_id != workspace_id:
            raise IssueError("parent_issue de outro workspace")
    if project_id:
        project = await db.get(Project, project_id)
        if project is None or project.workspace_id != workspace_id:
            raise IssueError("project não encontrado neste workspace", 404)

    await get_workspace(db, workspace_id)
    key = await _next_key(db, workspace_id)
    position = await _next_position(db, workspace_id, status)
    issue = Issue(
        workspace_id=workspace_id,
        key=key,
        title=title.strip(),
        description=description or "",
        status=status,
        priority=priority,
        assignee_type=assignee_type,
        assignee_id=assignee_id,
        creator_type=actor_type,
        creator_id=actor_id,
        parent_issue_id=parent_issue_id,
        project_id=project_id or None,
        position=position,
        meta={},
    )
    db.add(issue)
    await db.flush()

    if label_ids:
        for lid in set(label_ids):
            label = await db.get(Label, lid)
            if label and label.workspace_id == workspace_id:
                db.add(IssueLabel(issue_id=issue.id, label_id=lid))

    await _log(db, workspace_id, actor_type, actor_id, "created", {"key": key, "title": issue.title}, issue.id)

    # auto-subscribe: criador, assignee e @mencionados na descrição
    if actor_type in ("member", "agent"):
        await subscribe(db, issue.id, actor_type, actor_id, "creator")
    if issue.assignee_type in ("member", "agent") and issue.assignee_id:
        await subscribe(db, issue.id, issue.assignee_type, issue.assignee_id, "assignee")
    await _auto_subscribe_mentions(db, issue, issue.description)

    task = await _maybe_enqueue_agent_task(db, issue, actor_type, actor_id)
    await db.commit()
    await hub.publish(workspace_id, "issue:created", issue_to_dict(issue))
    if task:
        await _publish_task_queued(task)
    return issue


async def list_issues(
    db: AsyncSession,
    workspace_id: str,
    *,
    status: str | None = None,
    assignee_type: str | None = None,
    assignee_id: str | None = None,
    label_id: str | None = None,
    parent_issue_id: str | None = None,
    project_id: str | None = None,
    q: str | None = None,
) -> list[Issue]:
    stmt = select(Issue).where(Issue.workspace_id == workspace_id)
    if status:
        stmt = stmt.where(Issue.status == status)
    if assignee_type:
        stmt = stmt.where(Issue.assignee_type == assignee_type)
    if assignee_id:
        stmt = stmt.where(Issue.assignee_id == assignee_id)
    if parent_issue_id:
        stmt = stmt.where(Issue.parent_issue_id == parent_issue_id)
    if project_id:
        stmt = stmt.where(Issue.project_id == project_id)
    if label_id:
        stmt = stmt.join(IssueLabel, IssueLabel.issue_id == Issue.id).where(IssueLabel.label_id == label_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Issue.title.ilike(like) | Issue.key.ilike(like))
    stmt = stmt.order_by(Issue.status, Issue.position)
    rows = await db.execute(stmt)
    return list(rows.scalars())


async def update_issue(
    db: AsyncSession,
    issue_id: str,
    actor_type: str,
    actor_id: str,
    changes: dict[str, Any],
) -> Issue:
    """Aplica mudanças parciais. Campos aceitos: title, description, status, priority,
    assignee_type+assignee_id, parent_issue_id, position, due_date."""
    issue = await get_issue(db, issue_id)
    payload: dict[str, Any] = {}
    task: AgentTask | None = None

    if "title" in changes:
        title = (changes["title"] or "").strip()
        if not title:
            raise IssueError("title não pode ser vazio")
        payload["title"] = {"from": issue.title, "to": title}
        issue.title = title
    if "description" in changes:
        issue.description = changes["description"] or ""
        payload["description"] = True
    if "priority" in changes:
        if changes["priority"] not in PRIORITIES:
            raise IssueError(f"priority inválida: {changes['priority']}")
        payload["priority"] = {"from": issue.priority, "to": changes["priority"]}
        issue.priority = changes["priority"]
    if "assignee_type" in changes or "assignee_id" in changes:
        at = changes.get("assignee_type", issue.assignee_type)
        aid = changes.get("assignee_id", issue.assignee_id)
        if at in ("", None):
            at, aid = None, None
        if at not in (None, "member", "agent", "squad"):
            raise IssueError(f"assignee_type inválido: {at}")
        if (at is None) != (aid in (None, "")):
            raise IssueError("assignee_type e assignee_id devem vir juntos")
        if at == "squad" and aid:
            await _validate_squad(db, issue.workspace_id, aid)
        payload["assignee"] = {
            "from": {"type": issue.assignee_type, "id": issue.assignee_id},
            "to": {"type": at, "id": aid},
        }
        issue.assignee_type = at
        issue.assignee_id = aid or None
    if "parent_issue_id" in changes:
        pid = changes["parent_issue_id"] or None
        if pid:
            if pid == issue.id:
                raise IssueError("issue não pode ser pai de si mesma")
            parent = await get_issue(db, pid)
            if parent.workspace_id != issue.workspace_id:
                raise IssueError("parent_issue de outro workspace")
        payload["parent_issue_id"] = {"from": issue.parent_issue_id, "to": pid}
        issue.parent_issue_id = pid
    if "project_id" in changes:
        prj_id = changes["project_id"] or None
        if prj_id:
            project = await db.get(Project, prj_id)
            if project is None or project.workspace_id != issue.workspace_id:
                raise IssueError("project não encontrado neste workspace", 404)
        payload["project_id"] = {"from": issue.project_id, "to": prj_id}
        issue.project_id = prj_id
    if "due_date" in changes:
        issue.due_date = changes["due_date"]
        payload["due_date"] = str(changes["due_date"]) if changes["due_date"] else None
    if "position" in changes and changes["position"] is not None:
        issue.position = float(changes["position"])
        payload["position"] = issue.position
    if "status" in changes:
        st = changes["status"]
        if st not in ISSUE_STATUSES:
            raise IssueError(f"status inválido: {st}")
        if st != issue.status:
            payload["status"] = {"from": issue.status, "to": st}
            issue.status = st
            if "position" not in changes:
                issue.position = await _next_position(db, issue.workspace_id, st)

    if not payload:
        return issue

    action = "status_changed" if "status" in payload else (
        "assigned" if "assignee" in payload else "updated"
    )
    await _log(db, issue.workspace_id, actor_type, actor_id, action, payload, issue.id)

    # auto-subscribe: novo assignee e novos @mencionados na descrição
    if "assignee" in payload and issue.assignee_type in ("member", "agent") and issue.assignee_id:
        await subscribe(db, issue.id, issue.assignee_type, issue.assignee_id, "assignee")
    if "description" in payload:
        await _auto_subscribe_mentions(db, issue, issue.description)

    # regra multica: agente designado + status executável → enfileira task
    if "status" in payload or "assignee" in payload:
        task = await _maybe_enqueue_agent_task(db, issue, actor_type, actor_id)

    await db.commit()
    await hub.publish(issue.workspace_id, "issue:updated", issue_to_dict(issue))
    if task:
        await _publish_task_queued(task)
    return issue


async def move_issue(
    db: AsyncSession,
    issue_id: str,
    actor_type: str,
    actor_id: str,
    *,
    status: str,
    before_id: str | None = None,
    after_id: str | None = None,
) -> Issue:
    """Drag-and-drop: posiciona entre vizinhos (média das positions)."""
    issue = await get_issue(db, issue_id)
    if status not in ISSUE_STATUSES:
        raise IssueError(f"status inválido: {status}")

    before_pos = after_pos = None
    if after_id:  # card acima (posição menor)
        after = await get_issue(db, after_id)
        after_pos = after.position
    if before_id:  # card abaixo (posição maior)
        before = await get_issue(db, before_id)
        before_pos = before.position

    if after_pos is not None and before_pos is not None:
        position = (after_pos + before_pos) / 2.0
    elif after_pos is not None:  # solto no fim
        position = after_pos + POSITION_STEP
    elif before_pos is not None:  # solto no topo
        position = before_pos / 2.0 if before_pos > 0 else before_pos - POSITION_STEP
    else:  # coluna vazia
        position = await _next_position(db, issue.workspace_id, status)

    return await update_issue(db, issue_id, actor_type, actor_id, {"status": status, "position": position})


async def delete_issue(db: AsyncSession, issue_id: str, actor_type: str, actor_id: str) -> None:
    from ryu.services import attachments as att_svc

    issue = await get_issue(db, issue_id)
    ws_id, key = issue.workspace_id, issue.key
    # GC: attachments da issue (inclui os dos comentários, que carregam issue_id)
    orphan_atts = await att_svc.collect_for_issue(db, issue_id)
    await att_svc.delete_rows_for_issue(db, issue_id)
    await db.execute(delete(IssueSubscriber).where(IssueSubscriber.issue_id == issue_id))
    await db.execute(delete(IssueReaction).where(IssueReaction.issue_id == issue_id))
    comment_ids = [
        cid for (cid,) in (await db.execute(select(Comment.id).where(Comment.issue_id == issue_id)))
    ]
    if comment_ids:
        await db.execute(delete(CommentReaction).where(CommentReaction.comment_id.in_(comment_ids)))
    await db.execute(delete(IssueLabel).where(IssueLabel.issue_id == issue_id))
    await db.execute(delete(Comment).where(Comment.issue_id == issue_id))
    await db.execute(update(Issue).where(Issue.parent_issue_id == issue_id).values(parent_issue_id=None))
    await db.delete(issue)
    await _log(db, ws_id, actor_type, actor_id, "deleted", {"key": key}, issue_id)
    await db.commit()
    for att in orphan_atts:  # binários: best-effort após o commit
        await att_svc.delete_stored(att)
    await hub.publish(ws_id, "issue:deleted", {"id": issue_id, "key": key})


# ── Metadata KV ───────────────────────────────────────────────────────
def _validate_meta_key(key: str) -> None:
    if not key:
        raise IssueError("meta key é obrigatória")
    if not METADATA_KEY_RE.match(key):
        raise IssueError("meta key deve casar ^[a-zA-Z_][a-zA-Z0-9_.-]{0,63}$")


def _validate_meta_value(value: Any) -> None:
    """Valores só primitivos (string/number/bool). Remoção usa value=None/DELETE."""
    if isinstance(value, bool):
        return
    if isinstance(value, (str, int, float)):
        return
    raise IssueError("meta value deve ser primitivo: string, number ou bool")


async def set_issue_meta(
    db: AsyncSession, issue_id: str, actor_type: str, actor_id: str, key: str, value: Any
) -> dict:
    """PATCH single-key atômico: value=None remove a chave.

    Contrato (paridade multica): key regex, cap de 50 chaves, valores
    primitivos e bag serializado ≤ 8KB."""
    _validate_meta_key(key)
    issue = await get_issue(db, issue_id)
    meta = dict(issue.meta or {})
    if value is None:
        meta.pop(key, None)
    else:
        _validate_meta_value(value)
        if key not in meta and len(meta) >= MAX_METADATA_KEYS:
            raise IssueError(f"metadata não pode exceder {MAX_METADATA_KEYS} chaves")
        meta[key] = value
        if len(json.dumps(meta)) > MAX_METADATA_BYTES:
            raise IssueError(f"metadata excede {MAX_METADATA_BYTES} bytes")
    issue.meta = meta  # reatribui p/ marcar JSON como dirty
    await _log(db, issue.workspace_id, actor_type, actor_id, "meta_updated", {"key": key, "value": value}, issue.id)
    await db.commit()
    await hub.publish(issue.workspace_id, "issue:updated", issue_to_dict(issue))
    return meta


async def delete_issue_meta(
    db: AsyncSession, issue_id: str, actor_type: str, actor_id: str, key: str
) -> dict:
    return await set_issue_meta(db, issue_id, actor_type, actor_id, key, None)


# ── Labels ────────────────────────────────────────────────────────────
async def create_label(db: AsyncSession, workspace_id: str, actor_type: str, actor_id: str, name: str, color: str = "#8b5cf6") -> Label:
    if not name.strip():
        raise IssueError("name é obrigatório")
    label = Label(workspace_id=workspace_id, name=name.strip(), color=color)
    db.add(label)
    await db.flush()
    await _log(db, workspace_id, actor_type, actor_id, "label_created", {"label_id": label.id, "name": label.name})
    await db.commit()
    return label


async def list_labels(db: AsyncSession, workspace_id: str) -> list[Label]:
    rows = await db.execute(select(Label).where(Label.workspace_id == workspace_id).order_by(Label.name))
    return list(rows.scalars())


async def update_label(db: AsyncSession, label_id: str, actor_type: str, actor_id: str, name: str | None = None, color: str | None = None) -> Label:
    label = await db.get(Label, label_id)
    if label is None:
        raise IssueError("label não encontrada", 404)
    if name is not None and name.strip():
        label.name = name.strip()
    if color is not None:
        label.color = color
    await _log(db, label.workspace_id, actor_type, actor_id, "label_updated", {"label_id": label.id})
    await db.commit()
    return label


async def delete_label(db: AsyncSession, label_id: str, actor_type: str, actor_id: str) -> None:
    label = await db.get(Label, label_id)
    if label is None:
        raise IssueError("label não encontrada", 404)
    ws_id = label.workspace_id
    await db.execute(delete(IssueLabel).where(IssueLabel.label_id == label_id))
    await db.delete(label)
    await _log(db, ws_id, actor_type, actor_id, "label_deleted", {"label_id": label_id})
    await db.commit()


async def attach_label(db: AsyncSession, issue_id: str, label_id: str, actor_type: str, actor_id: str) -> None:
    issue = await get_issue(db, issue_id)
    label = await db.get(Label, label_id)
    if label is None or label.workspace_id != issue.workspace_id:
        raise IssueError("label não encontrada", 404)
    existing = await db.execute(
        select(IssueLabel).where(IssueLabel.issue_id == issue_id, IssueLabel.label_id == label_id)
    )
    if existing.first() is None:
        db.add(IssueLabel(issue_id=issue_id, label_id=label_id))
        await _log(db, issue.workspace_id, actor_type, actor_id, "label_attached", {"label_id": label_id}, issue_id)
        await db.commit()
        await hub.publish(issue.workspace_id, "issue:updated", issue_to_dict(issue))


async def detach_label(db: AsyncSession, issue_id: str, label_id: str, actor_type: str, actor_id: str) -> None:
    issue = await get_issue(db, issue_id)
    await db.execute(delete(IssueLabel).where(IssueLabel.issue_id == issue_id, IssueLabel.label_id == label_id))
    await _log(db, issue.workspace_id, actor_type, actor_id, "label_detached", {"label_id": label_id}, issue_id)
    await db.commit()
    await hub.publish(issue.workspace_id, "issue:updated", issue_to_dict(issue))


# ── Comentários ───────────────────────────────────────────────────────
async def create_comment(
    db: AsyncSession,
    issue_id: str,
    author_type: str,
    author_id: str,
    body: str,
    parent_comment_id: str | None = None,
) -> Comment:
    if not body.strip():
        raise IssueError("body é obrigatório")
    if author_type not in ("member", "agent", "system"):
        raise IssueError(f"author_type inválido: {author_type}")
    issue = await get_issue(db, issue_id)

    # squad leader evaluation: no_action registrado nesta rodada suprime o
    # comentário do líder (multica comment.go:1351)
    from ryu.services import squads as squads_svc  # lazy: evita ciclo

    if await squads_svc.should_suppress_leader_comment(db, issue, author_type, author_id):
        raise IssueError(
            "comentário suprimido: o líder registrou no_action para esta rodada", 409
        )

    if parent_comment_id:
        parent = await db.get(Comment, parent_comment_id)
        if parent is None or parent.issue_id != issue_id:
            raise IssueError("parent_comment inválido")
    comment = Comment(
        issue_id=issue_id,
        author_type=author_type,
        author_id=author_id,
        body=body.strip(),
        parent_comment_id=parent_comment_id,
    )
    db.add(comment)
    await db.flush()
    await _log(db, issue.workspace_id, author_type, author_id, "commented", {"comment_id": comment.id}, issue_id)

    # auto-subscribe: autor do comentário + @mencionados no corpo
    if author_type in ("member", "agent"):
        await subscribe(db, issue.id, author_type, author_id, "commenter")
    await _auto_subscribe_mentions(db, issue, body)

    await db.commit()
    await hub.publish(issue.workspace_id, "comment:created", comment_to_dict(comment))
    # loop de delegação: comentário em issue de squad (ou @squad) acorda o líder
    try:
        await squads_svc.handle_comment_squad_triggers(
            db, issue, author_type, author_id, body
        )
    except Exception:
        pass  # best-effort: trigger nunca derruba o comentário
    # fan-out do inbox p/ subscribers (base de notificações)
    await _notify_subscribers(
        db, issue, author_type, author_id,
        f"Novo comentário em {issue.key}", body.strip()[:280],
        group="comments",
    )
    return comment


async def list_comments(db: AsyncSession, issue_id: str) -> list[Comment]:
    rows = await db.execute(select(Comment).where(Comment.issue_id == issue_id).order_by(Comment.created_at))
    return list(rows.scalars())


# ── Comentários paginados thread-aware (paridade multica ListComments) ─
FLAT_COMMENTS_CAP = 2000


def _comment_key(c: Comment) -> tuple:
    return (c.created_at or c.id, c.id)


async def list_comments_paged(
    db: AsyncSession,
    issue_id: str,
    *,
    thread: str | None = None,
    tail: int | None = None,
    recent: int | None = None,
    before: Any = None,       # datetime | None (cursor)
    before_id: str | None = None,
    since: Any = None,        # datetime | None (polling incremental)
) -> dict:
    """Modos de leitura thread-aware com cursor (multica comment.go ListComments).

    - thread=<id>: raiz + descendentes; âncora pode ser qualquer reply (sobe até
      a raiz). tail=N limita às N réplicas mais recentes (raiz sempre incluída);
      before/before_id paginam réplicas mais antigas.
    - recent=N: N threads mais ativas (raiz + descendentes), oldest-active
      primeiro; before/before_id são cursor de THREAD (last_activity, root_id).
    - since=<ts>: filtra réplicas criadas <= ts (raiz isenta); suprime cursor
      quando a página seguinte só teria linhas mais antigas que o watermark.

    Retorna {"comments": [Comment...], "next_before": datetime|None,
             "next_before_id": str|None}.
    Cursor emitido SÓ quando existe página mais antiga de fato.
    """
    if thread and recent:
        raise IssueError("thread e recent são mutuamente exclusivos")
    if (before is not None or before_id) and not (recent or (thread and tail is not None)):
        raise IssueError("before/before_id só valem com recent=N ou thread+tail")

    all_comments = await list_comments(db, issue_id)
    by_id = {c.id: c for c in all_comments}

    def _root_of(c: Comment) -> Comment:
        seen = set()
        cur = c
        while cur.parent_comment_id and cur.parent_comment_id in by_id and cur.id not in seen:
            seen.add(cur.id)
            cur = by_id[cur.parent_comment_id]
        return cur

    # agrupa por thread (root_id -> [membros ordenados])
    threads: dict[str, list[Comment]] = {}
    for c in all_comments:
        threads.setdefault(_root_of(c).id, []).append(c)
    for members in threads.values():
        members.sort(key=_comment_key)

    def _norm(dt):
        if dt is None:
            return None
        from datetime import timezone as _tz

        return dt.replace(tzinfo=_tz.utc) if dt.tzinfo is None else dt

    before = _norm(before)
    since = _norm(since)

    if thread:
        anchor = by_id.get(thread)
        if anchor is None:
            raise IssueError("comentário não encontrado", 404)
        root = _root_of(anchor)
        members = threads.get(root.id, [root])
        replies = [c for c in members if c.id != root.id]
        # cursor de réplicas: só as estritamente mais antigas que (before, before_id)
        if before is not None:
            def _older(c: Comment) -> bool:
                created = _norm(c.created_at)
                if created is None:
                    return False
                if created < before:
                    return True
                return created == before and before_id is not None and c.id < before_id
            replies = [c for c in replies if _older(c)]
        next_before = next_before_id = None
        if tail is not None:
            tail = max(0, tail)
            page = replies[-tail:] if tail else []
            if len(replies) > len(page) and page:
                first = page[0]
                next_before, next_before_id = _norm(first.created_at), first.id
            elif len(replies) > 0 and tail == 0:
                # raiz sempre volta; com tail=0 ainda há réplicas mais antigas
                last = replies[-1]
                next_before, next_before_id = _norm(last.created_at), last.id
        else:
            page = replies
        if since is not None:
            page = [c for c in page if (_norm(c.created_at) or since) > since]
            if next_before is not None and next_before <= since:
                next_before = next_before_id = None
        return {"comments": [root] + page, "next_before": next_before, "next_before_id": next_before_id}

    if recent:
        recent = max(1, recent)
        infos = []
        for root_id, members in threads.items():
            last_activity = max((_norm(c.created_at) for c in members if c.created_at), default=None)
            infos.append((last_activity, root_id, members))
        infos = [i for i in infos if i[0] is not None]
        if before is not None:
            infos = [
                i for i in infos
                if i[0] < before or (i[0] == before and before_id is not None and i[1] < before_id)
            ]
        infos.sort(key=lambda i: (i[0], i[1]), reverse=True)  # mais ativa primeiro
        page_threads = infos[:recent]
        next_before = next_before_id = None
        if len(infos) > len(page_threads) and page_threads:
            oldest = page_threads[-1]
            next_before, next_before_id = oldest[0], oldest[1]
        page_threads.reverse()  # oldest-active primeiro (arcos completos)
        out: list[Comment] = []
        for _la, root_id, members in page_threads:
            root = by_id[root_id]
            replies = [c for c in members if c.id != root_id]
            if since is not None:
                replies = [c for c in replies if (_norm(c.created_at) or since) > since]
            out.append(root)
            out.extend(replies)
        if since is not None and next_before is not None and next_before <= since:
            next_before = next_before_id = None
        return {"comments": out, "next_before": next_before, "next_before_id": next_before_id}

    # flat: timeline cronológica com hard cap
    flat = all_comments[:FLAT_COMMENTS_CAP]
    if since is not None:
        flat = [c for c in flat if (_norm(c.created_at) or since) > since]
    return {"comments": flat, "next_before": None, "next_before_id": None}


async def update_comment(db: AsyncSession, comment_id: str, actor_type: str, actor_id: str, body: str) -> Comment:
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise IssueError("comentário não encontrado", 404)
    if not body.strip():
        raise IssueError("body é obrigatório")
    comment.body = body.strip()
    issue = await get_issue(db, comment.issue_id)
    await _log(db, issue.workspace_id, actor_type, actor_id, "comment_updated", {"comment_id": comment.id}, issue.id)
    await db.commit()
    await hub.publish(issue.workspace_id, "issue:updated", issue_to_dict(issue))
    return comment


async def delete_comment(db: AsyncSession, comment_id: str, actor_type: str, actor_id: str) -> None:
    from ryu.services import attachments as att_svc

    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise IssueError("comentário não encontrado", 404)
    issue = await get_issue(db, comment.issue_id)
    orphan_atts = await att_svc.collect_for_comment(db, comment_id)
    await att_svc.delete_rows_for_comment(db, comment_id)
    await db.execute(delete(CommentReaction).where(CommentReaction.comment_id == comment_id))
    await db.execute(update(Comment).where(Comment.parent_comment_id == comment_id).values(parent_comment_id=None))
    await db.delete(comment)
    await _log(db, issue.workspace_id, actor_type, actor_id, "comment_deleted", {"comment_id": comment_id}, issue.id)
    await db.commit()
    for att in orphan_atts:
        await att_svc.delete_stored(att)
    await hub.publish(issue.workspace_id, "issue:updated", issue_to_dict(issue))


# ── Resolve/unresolve de thread ───────────────────────────────────────
async def resolve_comment(
    db: AsyncSession, comment_id: str, actor_type: str, actor_id: str, resolved: bool
) -> Comment:
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise IssueError("comentário não encontrado", 404)
    if comment.parent_comment_id is not None:
        raise IssueError("apenas o comentário raiz da thread pode ser resolvido")
    issue = await get_issue(db, comment.issue_id)
    if resolved:
        if comment.resolved_at is None:
            comment.resolved_at = now()
            comment.resolved_by_type = actor_type
            comment.resolved_by_id = actor_id
            await _log(
                db, issue.workspace_id, actor_type, actor_id,
                "comment_resolved", {"comment_id": comment.id}, issue.id,
            )
    else:
        if comment.resolved_at is not None:
            comment.resolved_at = None
            comment.resolved_by_type = None
            comment.resolved_by_id = None
            await _log(
                db, issue.workspace_id, actor_type, actor_id,
                "comment_unresolved", {"comment_id": comment.id}, issue.id,
            )
    await db.commit()
    await hub.publish(issue.workspace_id, "comment:updated", comment_to_dict(comment))
    return comment


# ── Reactions (emoji) ─────────────────────────────────────────────────
def _reaction_summary(rows: Sequence) -> list[dict]:
    agg: dict[str, dict] = {}
    for r in rows:
        entry = agg.setdefault(r.emoji, {"emoji": r.emoji, "count": 0, "actors": []})
        entry["count"] += 1
        entry["actors"].append({"type": r.actor_type, "id": r.actor_id})
    return list(agg.values())


async def issue_reactions(db: AsyncSession, issue_id: str) -> list[dict]:
    rows = await db.execute(
        select(IssueReaction).where(IssueReaction.issue_id == issue_id).order_by(IssueReaction.created_at)
    )
    return _reaction_summary(list(rows.scalars()))


async def comment_reactions_map(db: AsyncSession, comment_ids: Sequence[str]) -> dict[str, list[dict]]:
    if not comment_ids:
        return {}
    rows = await db.execute(
        select(CommentReaction)
        .where(CommentReaction.comment_id.in_(list(comment_ids)))
        .order_by(CommentReaction.created_at)
    )
    by_comment: dict[str, list] = {}
    for r in rows.scalars():
        by_comment.setdefault(r.comment_id, []).append(r)
    return {cid: _reaction_summary(rs) for cid, rs in by_comment.items()}


def _validate_emoji(emoji: str) -> str:
    emoji = (emoji or "").strip()
    if not emoji or len(emoji) > 64:
        raise IssueError("emoji é obrigatório (máx 64 chars)")
    return emoji


async def add_issue_reaction(
    db: AsyncSession, issue_id: str, actor_type: str, actor_id: str, emoji: str
) -> list[dict]:
    emoji = _validate_emoji(emoji)
    if actor_type not in ("member", "agent"):
        raise IssueError(f"actor_type inválido: {actor_type}")
    issue = await get_issue(db, issue_id)
    existing = await db.execute(
        select(IssueReaction).where(
            IssueReaction.issue_id == issue_id,
            IssueReaction.actor_type == actor_type,
            IssueReaction.actor_id == actor_id,
            IssueReaction.emoji == emoji,
        )
    )
    if existing.scalars().first() is None:
        db.add(
            IssueReaction(
                issue_id=issue_id, workspace_id=issue.workspace_id,
                actor_type=actor_type, actor_id=actor_id, emoji=emoji,
            )
        )
        await db.commit()
        await hub.publish(
            issue.workspace_id, "issue:reaction",
            {"issue_id": issue_id, "emoji": emoji, "actor_type": actor_type, "actor_id": actor_id, "action": "added"},
        )
    return await issue_reactions(db, issue_id)


async def remove_issue_reaction(
    db: AsyncSession, issue_id: str, actor_type: str, actor_id: str, emoji: str
) -> list[dict]:
    emoji = _validate_emoji(emoji)
    issue = await get_issue(db, issue_id)
    await db.execute(
        delete(IssueReaction).where(
            IssueReaction.issue_id == issue_id,
            IssueReaction.actor_type == actor_type,
            IssueReaction.actor_id == actor_id,
            IssueReaction.emoji == emoji,
        )
    )
    await db.commit()
    await hub.publish(
        issue.workspace_id, "issue:reaction",
        {"issue_id": issue_id, "emoji": emoji, "actor_type": actor_type, "actor_id": actor_id, "action": "removed"},
    )
    return await issue_reactions(db, issue_id)


async def add_comment_reaction(
    db: AsyncSession, comment_id: str, actor_type: str, actor_id: str, emoji: str
) -> list[dict]:
    emoji = _validate_emoji(emoji)
    if actor_type not in ("member", "agent"):
        raise IssueError(f"actor_type inválido: {actor_type}")
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise IssueError("comentário não encontrado", 404)
    issue = await get_issue(db, comment.issue_id)
    existing = await db.execute(
        select(CommentReaction).where(
            CommentReaction.comment_id == comment_id,
            CommentReaction.actor_type == actor_type,
            CommentReaction.actor_id == actor_id,
            CommentReaction.emoji == emoji,
        )
    )
    if existing.scalars().first() is None:
        db.add(
            CommentReaction(
                comment_id=comment_id, workspace_id=issue.workspace_id,
                actor_type=actor_type, actor_id=actor_id, emoji=emoji,
            )
        )
        await db.commit()
        await hub.publish(
            issue.workspace_id, "comment:reaction",
            {"comment_id": comment_id, "issue_id": issue.id, "emoji": emoji,
             "actor_type": actor_type, "actor_id": actor_id, "action": "added"},
        )
    return (await comment_reactions_map(db, [comment_id])).get(comment_id, [])


async def remove_comment_reaction(
    db: AsyncSession, comment_id: str, actor_type: str, actor_id: str, emoji: str
) -> list[dict]:
    emoji = _validate_emoji(emoji)
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise IssueError("comentário não encontrado", 404)
    issue = await get_issue(db, comment.issue_id)
    await db.execute(
        delete(CommentReaction).where(
            CommentReaction.comment_id == comment_id,
            CommentReaction.actor_type == actor_type,
            CommentReaction.actor_id == actor_id,
            CommentReaction.emoji == emoji,
        )
    )
    await db.commit()
    await hub.publish(
        issue.workspace_id, "comment:reaction",
        {"comment_id": comment_id, "issue_id": issue.id, "emoji": emoji,
         "actor_type": actor_type, "actor_id": actor_id, "action": "removed"},
    )
    return (await comment_reactions_map(db, [comment_id])).get(comment_id, [])


# ── Batch operations ──────────────────────────────────────────────────
async def batch_update_issues(
    db: AsyncSession,
    workspace_id: str,
    actor_type: str,
    actor_id: str,
    issue_ids: Sequence[str],
    changes: dict[str, Any],
) -> list[Issue]:
    """Aplica mudanças comuns a N issues numa transação única.

    Campos: status, priority, assignee_type+assignee_id, project_id,
    due_date, add_label_ids, remove_label_ids. Activity log por issue;
    eventos realtime publicados após o commit."""
    if not issue_ids:
        raise IssueError("issue_ids é obrigatório")
    if len(issue_ids) > 200:
        raise IssueError("máximo de 200 issues por batch")

    # validações compartilhadas (uma vez só)
    if "status" in changes and changes["status"] not in ISSUE_STATUSES:
        raise IssueError(f"status inválido: {changes['status']}")
    if "priority" in changes and changes["priority"] not in PRIORITIES:
        raise IssueError(f"priority inválida: {changes['priority']}")
    if "assignee_type" in changes or "assignee_id" in changes:
        at = changes.get("assignee_type") or None
        aid = changes.get("assignee_id") or None
        if at not in (None, "member", "agent", "squad"):
            raise IssueError(f"assignee_type inválido: {at}")
        if (at is None) != (aid is None):
            raise IssueError("assignee_type e assignee_id devem vir juntos")
        if at == "squad" and aid:
            await _validate_squad(db, workspace_id, aid)
    if changes.get("project_id"):
        project = await db.get(Project, changes["project_id"])
        if project is None or project.workspace_id != workspace_id:
            raise IssueError("project não encontrado neste workspace", 404)
    add_labels: list[str] = list(changes.get("add_label_ids") or [])
    remove_labels: list[str] = list(changes.get("remove_label_ids") or [])
    for lid in add_labels:
        label = await db.get(Label, lid)
        if label is None or label.workspace_id != workspace_id:
            raise IssueError(f"label não encontrada: {lid}", 404)

    rows = await db.execute(
        select(Issue).where(Issue.id.in_(list(issue_ids)), Issue.workspace_id == workspace_id)
    )
    issues = list(rows.scalars())
    if len(issues) != len(set(issue_ids)):
        raise IssueError("uma ou mais issues não encontradas neste workspace", 404)

    tasks: list[AgentTask] = []
    for issue in issues:
        payload: dict[str, Any] = {}
        if "priority" in changes and changes["priority"] != issue.priority:
            payload["priority"] = {"from": issue.priority, "to": changes["priority"]}
            issue.priority = changes["priority"]
        if "assignee_type" in changes or "assignee_id" in changes:
            at = changes.get("assignee_type") or None
            aid = changes.get("assignee_id") or None
            if (at, aid) != (issue.assignee_type, issue.assignee_id):
                payload["assignee"] = {
                    "from": {"type": issue.assignee_type, "id": issue.assignee_id},
                    "to": {"type": at, "id": aid},
                }
                issue.assignee_type = at
                issue.assignee_id = aid
                if at:
                    await subscribe(db, issue.id, at, aid, "assignee")
        if "project_id" in changes:
            pid = changes["project_id"] or None
            if pid != issue.project_id:
                payload["project_id"] = {"from": issue.project_id, "to": pid}
                issue.project_id = pid
        if "due_date" in changes:
            issue.due_date = changes["due_date"]
            payload["due_date"] = str(changes["due_date"]) if changes["due_date"] else None
        if "status" in changes and changes["status"] != issue.status:
            payload["status"] = {"from": issue.status, "to": changes["status"]}
            issue.status = changes["status"]
            issue.position = await _next_position(db, issue.workspace_id, issue.status)
        for lid in add_labels:
            existing = await db.execute(
                select(IssueLabel).where(IssueLabel.issue_id == issue.id, IssueLabel.label_id == lid)
            )
            if existing.first() is None:
                db.add(IssueLabel(issue_id=issue.id, label_id=lid))
                payload.setdefault("labels_added", []).append(lid)
        if remove_labels:
            await db.execute(
                delete(IssueLabel).where(
                    IssueLabel.issue_id == issue.id, IssueLabel.label_id.in_(remove_labels)
                )
            )
            payload["labels_removed"] = remove_labels

        if payload:
            action = "status_changed" if "status" in payload else (
                "assigned" if "assignee" in payload else "updated"
            )
            await _log(db, issue.workspace_id, actor_type, actor_id, action, payload, issue.id)
            if "status" in payload or "assignee" in payload:
                task = await _maybe_enqueue_agent_task(db, issue, actor_type, actor_id)
                if task:
                    tasks.append(task)

    await db.commit()
    for issue in issues:
        await hub.publish(issue.workspace_id, "issue:updated", issue_to_dict(issue))
    for task in tasks:
        await _publish_task_queued(task)
    return issues


async def batch_delete_issues(
    db: AsyncSession,
    workspace_id: str,
    actor_type: str,
    actor_id: str,
    issue_ids: Sequence[str],
) -> int:
    if not issue_ids:
        raise IssueError("issue_ids é obrigatório")
    if len(issue_ids) > 200:
        raise IssueError("máximo de 200 issues por batch")
    rows = await db.execute(
        select(Issue).where(Issue.id.in_(list(issue_ids)), Issue.workspace_id == workspace_id)
    )
    issues = list(rows.scalars())
    if len(issues) != len(set(issue_ids)):
        raise IssueError("uma ou mais issues não encontradas neste workspace", 404)

    from ryu.services import attachments as att_svc

    orphan_atts = []
    deleted: list[tuple[str, str]] = []
    for issue in issues:
        iid = issue.id
        orphan_atts.extend(await att_svc.collect_for_issue(db, iid))
        await att_svc.delete_rows_for_issue(db, iid)
        await db.execute(delete(IssueSubscriber).where(IssueSubscriber.issue_id == iid))
        await db.execute(delete(IssueReaction).where(IssueReaction.issue_id == iid))
        comment_ids = [
            cid for (cid,) in (await db.execute(select(Comment.id).where(Comment.issue_id == iid)))
        ]
        if comment_ids:
            await db.execute(delete(CommentReaction).where(CommentReaction.comment_id.in_(comment_ids)))
        await db.execute(delete(IssueLabel).where(IssueLabel.issue_id == iid))
        await db.execute(delete(Comment).where(Comment.issue_id == iid))
        await db.execute(update(Issue).where(Issue.parent_issue_id == iid).values(parent_issue_id=None))
        await _log(db, workspace_id, actor_type, actor_id, "deleted", {"key": issue.key}, iid)
        deleted.append((iid, issue.key))
        await db.delete(issue)

    await db.commit()  # transação única p/ o lote inteiro
    for att in orphan_atts:
        await att_svc.delete_stored(att)
    for iid, key in deleted:
        await hub.publish(workspace_id, "issue:deleted", {"id": iid, "key": key})
    return len(deleted)


# ── Query avançada / paginação ────────────────────────────────────────
_PRIORITY_ORDER = case(
    {"urgent": 0, "high": 1, "medium": 2, "low": 3, "none": 4},
    value=Issue.priority,
    else_=5,
)


def _apply_filters(
    stmt,
    workspace_id: str,
    *,
    statuses: Sequence[str] | None = None,
    priorities: Sequence[str] | None = None,
    assignee_ids: Sequence[str] | None = None,
    assignee_type: str | None = None,
    creator_id: str | None = None,
    creator_type: str | None = None,
    involves_user_id: str | None = None,
    project_ids: Sequence[str] | None = None,
    include_no_project: bool = False,
    label_ids: Sequence[str] | None = None,
    parent_issue_id: str | None = None,
    ids: Sequence[str] | None = None,
    metadata: dict | None = None,
    properties: dict | None = None,
    top_level_only: bool = False,
    open_only: bool = False,
    scheduled: bool = False,
    q: str | None = None,
):
    stmt = stmt.where(Issue.workspace_id == workspace_id)
    if statuses:
        stmt = stmt.where(Issue.status.in_(list(statuses)))
    if priorities:
        stmt = stmt.where(Issue.priority.in_(list(priorities)))
    if assignee_type:
        stmt = stmt.where(Issue.assignee_type == assignee_type)
    if assignee_ids:
        conds = []
        plain = []
        for a in assignee_ids:
            if a in ("none", "unassigned", "no_assignee"):
                conds.append(Issue.assignee_id.is_(None))
            elif ":" in a:
                at, aid = a.split(":", 1)
                conds.append((Issue.assignee_type == at) & (Issue.assignee_id == aid))
            else:
                plain.append(a)
        if plain:
            conds.append(Issue.assignee_id.in_(plain))
        stmt = stmt.where(or_(*conds))
    if creator_id:
        stmt = stmt.where(Issue.creator_id == creator_id)
    if creator_type:
        stmt = stmt.where(Issue.creator_type == creator_type)
    if involves_user_id:
        commented = exists(
            select(Comment.id).where(Comment.issue_id == Issue.id, Comment.author_id == involves_user_id)
        )
        stmt = stmt.where(
            or_(
                Issue.creator_id == involves_user_id,
                Issue.assignee_id == involves_user_id,
                commented,
            )
        )
    if project_ids or include_no_project:
        conds = []
        if project_ids:
            conds.append(Issue.project_id.in_(list(project_ids)))
        if include_no_project:
            conds.append(Issue.project_id.is_(None))
        stmt = stmt.where(or_(*conds))
    if label_ids:
        labeled = exists(
            select(IssueLabel.issue_id).where(
                IssueLabel.issue_id == Issue.id, IssueLabel.label_id.in_(list(label_ids))
            )
        )
        stmt = stmt.where(labeled)
    if parent_issue_id:
        stmt = stmt.where(Issue.parent_issue_id == parent_issue_id)
    if ids:
        stmt = stmt.where(Issue.id.in_(list(ids)))
    if metadata:
        for k, v in metadata.items():
            if isinstance(v, (dict, list)):
                raise IssueError("metadata filter aceita apenas valores primitivos")
            stmt = stmt.where(func.json_extract(Issue.meta, f"$.{k}") == v)
    if properties:
        for pid, v in properties.items():
            col = func.json_extract(Issue.properties, f"$.{pid}")
            if isinstance(v, list):
                # multi_select: qualquer um dos valores presente no array serializado
                conds = [
                    func.json_extract(Issue.properties, f"$.{pid}").like(f'%"{item}"%') for item in v
                ]
                stmt = stmt.where(or_(*conds))
            elif isinstance(v, bool):
                stmt = stmt.where(col == (1 if v else 0))
            else:
                stmt = stmt.where(col == v)
    if top_level_only:
        stmt = stmt.where(Issue.parent_issue_id.is_(None))
    if open_only:
        stmt = stmt.where(Issue.status.in_(OPEN_STATUSES))
    if scheduled:
        stmt = stmt.where(Issue.due_date.is_not(None))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Issue.title.ilike(like) | Issue.key.ilike(like) | Issue.description.ilike(like))
    return stmt


def _apply_sort(stmt, sort: str | None, direction: str | None):
    direction = (direction or "asc").lower()
    if direction not in ("asc", "desc"):
        raise IssueError("direction deve ser asc|desc")
    desc = direction == "desc"

    def d(col):
        return col.desc() if desc else col.asc()

    sort = sort or "position"
    if sort not in SORT_FIELDS:
        raise IssueError(f"sort inválido: {sort} (aceitos: {', '.join(SORT_FIELDS)})")
    if sort == "created":
        return stmt.order_by(d(Issue.created_at), Issue.id)
    if sort == "updated":
        return stmt.order_by(d(Issue.updated_at), Issue.id)
    if sort == "priority":
        return stmt.order_by(_PRIORITY_ORDER.desc() if desc else _PRIORITY_ORDER.asc(), Issue.position)
    if sort == "due_date":
        return stmt.order_by(Issue.due_date.is_(None), d(Issue.due_date), Issue.id)
    return stmt.order_by(Issue.status, d(Issue.position))


async def query_issues(
    db: AsyncSession,
    workspace_id: str,
    *,
    sort: str | None = None,
    direction: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    **filters,
) -> tuple[list[Issue], int]:
    """Listagem com filtros multi-valor, ordenação e paginação. Retorna (items, total)."""
    base = _apply_filters(select(Issue), workspace_id, **filters)
    total = int(
        (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    stmt = _apply_sort(base, sort, direction)
    if limit is not None:
        stmt = stmt.limit(max(1, min(int(limit), 500))).offset(max(0, int(offset)))
    rows = await db.execute(stmt)
    return list(rows.scalars()), total


# ── Board/tabela agrupada + facets ────────────────────────────────────
async def _group_keys(db: AsyncSession, workspace_id: str, group_by: str, base_filters: dict):
    """Retorna [(key, count)] respeitando os filtros da listagem."""
    if group_by not in GROUP_BY_FIELDS:
        raise IssueError(f"group_by inválido: {group_by} (aceitos: {', '.join(GROUP_BY_FIELDS)})")
    if group_by == "label":
        stmt = _apply_filters(
            select(IssueLabel.label_id, func.count(func.distinct(Issue.id)))
            .join(Issue, Issue.id == IssueLabel.issue_id),
            workspace_id,
            **base_filters,
        ).group_by(IssueLabel.label_id)
        rows = await db.execute(stmt)
        return [(lid, int(cnt)) for lid, cnt in rows.all()]
    col = {
        "status": Issue.status,
        "priority": Issue.priority,
        "project": Issue.project_id,
        "assignee": func.coalesce(Issue.assignee_type + ":" + Issue.assignee_id, "unassigned"),
    }[group_by]
    stmt = _apply_filters(select(col, func.count()), workspace_id, **base_filters).group_by(col)
    rows = await db.execute(stmt)
    return [(k if k is not None else "none", int(cnt)) for k, cnt in rows.all()]


def _group_filter(group_by: str, group_key: str) -> dict:
    """Converte (group_by, key) em filtro adicional p/ buscar as rows do grupo."""
    if group_by == "status":
        return {"statuses": [group_key]}
    if group_by == "priority":
        return {"priorities": [group_key]}
    if group_by == "label":
        return {"label_ids": [group_key]}
    if group_by == "project":
        if group_key in ("none", "no_project"):
            return {"include_no_project": True}
        return {"project_ids": [group_key]}
    if group_by == "assignee":
        if group_key in ("unassigned", "none"):
            return {"assignee_ids": ["none"]}
        return {"assignee_ids": [group_key]}
    raise IssueError(f"group_by inválido: {group_by}")


async def grouped_issues(
    db: AsyncSession,
    workspace_id: str,
    group_by: str,
    *,
    per_group_limit: int = 50,
    sort: str | None = None,
    direction: str | None = None,
    **filters,
) -> list[dict]:
    groups = []
    for key, count in await _group_keys(db, workspace_id, group_by, filters):
        gf = dict(filters)
        for fk, fv in _group_filter(group_by, str(key)).items():
            gf[fk] = fv
        items, _ = await query_issues(
            db, workspace_id, sort=sort, direction=direction,
            limit=per_group_limit, offset=0, **gf,
        )
        groups.append({"key": str(key), "count": count, "issues": [issue_to_dict(i) for i in items]})
    # ordena grupos por chave estável (status na ordem canônica, prioridade idem)
    if group_by == "status":
        order = {s: i for i, s in enumerate(ISSUE_STATUSES)}
        groups.sort(key=lambda g: order.get(g["key"], 99))
    elif group_by == "priority":
        order = {p: i for i, p in enumerate(PRIORITIES)}
        groups.sort(key=lambda g: order.get(g["key"], 99))
    else:
        groups.sort(key=lambda g: g["key"])
    return groups


async def table_groups(db: AsyncSession, workspace_id: str, group_by: str, **filters) -> list[dict]:
    return [
        {"key": str(k), "count": c} for k, c in await _group_keys(db, workspace_id, group_by, filters)
    ]


async def table_rows(
    db: AsyncSession,
    workspace_id: str,
    group_by: str | None,
    group_key: str | None,
    *,
    sort: str | None = None,
    direction: str | None = None,
    limit: int = 50,
    offset: int = 0,
    **filters,
) -> tuple[list[Issue], int]:
    if group_by and group_key is not None:
        for fk, fv in _group_filter(group_by, group_key).items():
            filters[fk] = fv
    return await query_issues(
        db, workspace_id, sort=sort, direction=direction, limit=limit, offset=offset, **filters
    )


async def table_facets(db: AsyncSession, workspace_id: str, **filters) -> dict:
    """Contagens por valor de filtro (p/ menus de filtro do board/tabela)."""
    facets: dict = {}
    for facet in ("status", "priority", "assignee", "project", "label"):
        entries = await _group_keys(db, workspace_id, facet, filters)
        facets[facet] = [{"value": str(k), "count": c} for k, c in entries]
    return facets


# ── Busca full-text (título + descrição + comentários) ────────────────
def _snippet(text: str, q: str, radius: int = 60) -> str:
    lower = text.lower()
    idx = lower.find(q.lower())
    if idx < 0:
        return text[: radius * 2]
    start = max(0, idx - radius)
    end = min(len(text), idx + len(q) + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


async def search_issues(
    db: AsyncSession, workspace_id: str, q: str, limit: int = 50
) -> list[dict]:
    """Busca em title/key/description e corpo de comentários (LIKE lower)."""
    q = (q or "").strip()
    if not q:
        return []
    limit = max(1, min(limit, 100))
    like = f"%{q.lower()}%"

    results: dict[str, dict] = {}

    rows = await db.execute(
        select(Issue)
        .where(
            Issue.workspace_id == workspace_id,
            or_(
                func.lower(Issue.title).like(like),
                func.lower(Issue.key).like(like),
                func.lower(Issue.description).like(like),
            ),
        )
        .order_by(Issue.updated_at.desc())
        .limit(limit)
    )
    for issue in rows.scalars():
        if q.lower() in (issue.title or "").lower() or q.lower() in (issue.key or "").lower():
            match, snip = "title", _snippet(issue.title, q)
        else:
            match, snip = "description", _snippet(issue.description or "", q)
        results[issue.id] = {"issue": issue_to_dict(issue), "match": match, "snippet": snip}

    if len(results) < limit:
        rows = await db.execute(
            select(Comment, Issue)
            .join(Issue, Issue.id == Comment.issue_id)
            .where(Issue.workspace_id == workspace_id, func.lower(Comment.body).like(like))
            .order_by(Comment.created_at.desc())
            .limit(limit)
        )
        for comment, issue in rows.all():
            if issue.id in results:
                continue
            results[issue.id] = {
                "issue": issue_to_dict(issue),
                "match": "comment",
                "snippet": _snippet(comment.body, q),
                "comment_id": comment.id,
            }
            if len(results) >= limit:
                break

    return list(results.values())[:limit]


# ── Activity ──────────────────────────────────────────────────────────
async def list_activity(db: AsyncSession, issue_id: str, limit: int = 100) -> list[ActivityLog]:
    rows = await db.execute(
        select(ActivityLog).where(ActivityLog.issue_id == issue_id).order_by(ActivityLog.created_at.desc()).limit(limit)
    )
    return list(rows.scalars())
