"""Serviço do domínio ISSUES/TRACKER.

Regras centrais:
- key gerada via workspace.issue_counter (incremento atômico via UPDATE ... RETURNING quando possível).
- toda mutação grava ActivityLog e publica no hub.
- assignee polimórfico (member|agent); quando agent + status todo/in_progress → cria AgentTask queued.
"""
from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.models import (
    ActivityLog,
    Agent,
    AgentTask,
    Comment,
    Issue,
    IssueLabel,
    Label,
    Project,
    Workspace,
)
from ryu.realtime.hub import hub

ISSUE_STATUSES = ["backlog", "todo", "in_progress", "in_review", "done", "blocked", "cancelled"]
PRIORITIES = ["urgent", "high", "medium", "low", "none"]

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
        "created_at": issue.created_at.isoformat() if issue.created_at else None,
        "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
    }
    if labels is not None:
        d["labels"] = [label_to_dict(lb) for lb in labels]
    return d


def label_to_dict(label: Label) -> dict:
    return {"id": label.id, "workspace_id": label.workspace_id, "name": label.name, "color": label.color}


def comment_to_dict(c: Comment) -> dict:
    return {
        "id": c.id,
        "issue_id": c.issue_id,
        "author_type": c.author_type,
        "author_id": c.author_id,
        "body": c.body,
        "parent_comment_id": c.parent_comment_id,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


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
    """Se assignee é agent e status é todo/in_progress, cria AgentTask queued (sem duplicar)."""
    if issue.assignee_type != "agent" or issue.assignee_id is None:
        return None
    if issue.status not in ("todo", "in_progress"):
        return None
    agent = await db.get(Agent, issue.assignee_id)
    if agent is None:
        return None
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
    if assignee_type not in (None, "member", "agent"):
        raise IssueError(f"assignee_type inválido: {assignee_type}")
    if (assignee_type is None) != (assignee_id is None):
        raise IssueError("assignee_type e assignee_id devem vir juntos")
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
        if at not in (None, "member", "agent"):
            raise IssueError(f"assignee_type inválido: {at}")
        if (at is None) != (aid in (None, "")):
            raise IssueError("assignee_type e assignee_id devem vir juntos")
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
    issue = await get_issue(db, issue_id)
    ws_id, key = issue.workspace_id, issue.key
    await db.execute(delete(IssueLabel).where(IssueLabel.issue_id == issue_id))
    await db.execute(delete(Comment).where(Comment.issue_id == issue_id))
    await db.execute(update(Issue).where(Issue.parent_issue_id == issue_id).values(parent_issue_id=None))
    await db.delete(issue)
    await _log(db, ws_id, actor_type, actor_id, "deleted", {"key": key}, issue_id)
    await db.commit()
    await hub.publish(ws_id, "issue:deleted", {"id": issue_id, "key": key})


# ── Metadata KV ───────────────────────────────────────────────────────
async def set_issue_meta(
    db: AsyncSession, issue_id: str, actor_type: str, actor_id: str, key: str, value: Any
) -> dict:
    """PATCH single-key atômico: value=None remove a chave."""
    if not key:
        raise IssueError("meta key é obrigatória")
    issue = await get_issue(db, issue_id)
    meta = dict(issue.meta or {})
    if value is None:
        meta.pop(key, None)
    else:
        meta[key] = value
    issue.meta = meta  # reatribui p/ marcar JSON como dirty
    await _log(db, issue.workspace_id, actor_type, actor_id, "meta_updated", {"key": key, "value": value}, issue.id)
    await db.commit()
    await hub.publish(issue.workspace_id, "issue:updated", issue_to_dict(issue))
    return meta


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
    await db.commit()
    await hub.publish(issue.workspace_id, "comment:created", comment_to_dict(comment))
    return comment


async def list_comments(db: AsyncSession, issue_id: str) -> list[Comment]:
    rows = await db.execute(select(Comment).where(Comment.issue_id == issue_id).order_by(Comment.created_at))
    return list(rows.scalars())


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
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise IssueError("comentário não encontrado", 404)
    issue = await get_issue(db, comment.issue_id)
    await db.execute(update(Comment).where(Comment.parent_comment_id == comment_id).values(parent_comment_id=None))
    await db.delete(comment)
    await _log(db, issue.workspace_id, actor_type, actor_id, "comment_deleted", {"comment_id": comment_id}, issue.id)
    await db.commit()
    await hub.publish(issue.workspace_id, "issue:updated", issue_to_dict(issue))


# ── Activity ──────────────────────────────────────────────────────────
async def list_activity(db: AsyncSession, issue_id: str, limit: int = 100) -> list[ActivityLog]:
    rows = await db.execute(
        select(ActivityLog).where(ActivityLog.issue_id == issue_id).order_by(ActivityLog.created_at.desc()).limit(limit)
    )
    return list(rows.scalars())
