"""Serviço do domínio INBOX + USAGE.

Exporta:
- notify(db, workspace_id, user_id, severity, title, body, issue_id) — cria item e publica inbox:new
- list_items / unread_count / mark_read / mark_all_read / archive_items
- usage_summary(db, workspace_id, days) — agregação on-the-fly de AgentTask
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.models import Agent, AgentTask, InboxItem, Issue, Member, NotificationPreference
from ryu.realtime.hub import hub

SEVERITIES = ["action_required", "attention", "info"]


class InboxError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def item_to_dict(item: InboxItem) -> dict:
    return {
        "id": item.id,
        "workspace_id": item.workspace_id,
        "user_id": item.user_id,
        "severity": item.severity,
        "title": item.title,
        "body": item.body,
        "issue_id": item.issue_id,
        "read": item.read,
        "archived": item.archived,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


# ── Preferências de notificação (multica notification_preference) ─────
async def is_muted(db: AsyncSession, workspace_id: str, user_id: str, group: str | None) -> bool:
    """True quando o grupo está 'muted' nas preferências do (workspace, user)."""
    if not group:
        return False
    res = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.workspace_id == workspace_id,
            NotificationPreference.user_id == user_id,
        )
    )
    row = res.scalars().first()
    if row is None:
        return False
    return (row.preferences or {}).get(group) == "muted"


# ── Notify (helper usado por outros domínios) ─────────────────────────
async def notify(
    db: AsyncSession,
    workspace_id: str,
    user_id: str,
    severity: str,
    title: str,
    body: str = "",
    issue_id: str | None = None,
    group: str | None = None,
) -> InboxItem | None:
    if severity not in SEVERITIES:
        severity = "info"
    # preferências: grupo mutado suprime a criação do item
    try:
        if await is_muted(db, workspace_id, user_id, group):
            return None
    except Exception:
        pass  # preferência nunca derruba a notificação
    item = InboxItem(
        workspace_id=workspace_id,
        user_id=user_id,
        severity=severity,
        title=title,
        body=body,
        issue_id=issue_id,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    await hub.publish(workspace_id, "inbox:new", item_to_dict(item))
    return item


# ── Consulta ──────────────────────────────────────────────────────────
async def list_items(
    db: AsyncSession,
    workspace_id: str,
    user_id: str,
    read: bool | None = None,
    severity: str | None = None,
    archived: bool = False,
    limit: int = 100,
) -> list[InboxItem]:
    stmt = select(InboxItem).where(
        InboxItem.workspace_id == workspace_id,
        InboxItem.user_id == user_id,
        InboxItem.archived == archived,
    )
    if read is not None:
        stmt = stmt.where(InboxItem.read == read)
    if severity:
        stmt = stmt.where(InboxItem.severity == severity)
    stmt = stmt.order_by(InboxItem.created_at.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars())


async def unread_count(db: AsyncSession, workspace_id: str, user_id: str) -> int:
    stmt = select(func.count()).select_from(InboxItem).where(
        InboxItem.workspace_id == workspace_id,
        InboxItem.user_id == user_id,
        InboxItem.read == False,  # noqa: E712
        InboxItem.archived == False,  # noqa: E712
    )
    return int((await db.execute(stmt)).scalar_one())


# ── Mutações em lote ──────────────────────────────────────────────────
async def mark_read(db: AsyncSession, user_id: str, item_ids: list[str], read: bool = True) -> int:
    if not item_ids:
        return 0
    res = await db.execute(
        update(InboxItem)
        .where(InboxItem.id.in_(item_ids), InboxItem.user_id == user_id)
        .values(read=read)
    )
    await db.commit()
    return res.rowcount or 0


async def mark_all_read(db: AsyncSession, workspace_id: str, user_id: str) -> int:
    res = await db.execute(
        update(InboxItem)
        .where(
            InboxItem.workspace_id == workspace_id,
            InboxItem.user_id == user_id,
            InboxItem.read == False,  # noqa: E712
        )
        .values(read=True)
    )
    await db.commit()
    return res.rowcount or 0


async def archive_items(db: AsyncSession, user_id: str, item_ids: list[str], archived: bool = True) -> int:
    if not item_ids:
        return 0
    res = await db.execute(
        update(InboxItem)
        .where(InboxItem.id.in_(item_ids), InboxItem.user_id == user_id)
        .values(archived=archived, read=True)
    )
    await db.commit()
    return res.rowcount or 0


async def unarchive_item(db: AsyncSession, user_id: str, item_id: str) -> InboxItem | None:
    """Restaura um item arquivado (mantém `read` intocado — paridade multica)."""
    res = await db.execute(
        select(InboxItem).where(InboxItem.id == item_id, InboxItem.user_id == user_id)
    )
    item = res.scalars().first()
    if item is None:
        return None
    item.archived = False
    await db.commit()
    await hub.publish(item.workspace_id, "inbox:unarchived", {"item_id": item.id})
    return item


async def archive_all(db: AsyncSession, workspace_id: str, user_id: str) -> int:
    res = await db.execute(
        update(InboxItem)
        .where(
            InboxItem.workspace_id == workspace_id,
            InboxItem.user_id == user_id,
            InboxItem.archived == False,  # noqa: E712
        )
        .values(archived=True)
    )
    await db.commit()
    return res.rowcount or 0


async def archive_all_read(db: AsyncSession, workspace_id: str, user_id: str) -> int:
    res = await db.execute(
        update(InboxItem)
        .where(
            InboxItem.workspace_id == workspace_id,
            InboxItem.user_id == user_id,
            InboxItem.archived == False,  # noqa: E712
            InboxItem.read == True,  # noqa: E712
        )
        .values(archived=True)
    )
    await db.commit()
    return res.rowcount or 0


async def archive_completed(db: AsyncSession, workspace_id: str, user_id: str) -> int:
    """Arquiva notificações cujas issues estão done/cancelled (multica)."""
    done_ids = select(Issue.id).where(
        Issue.workspace_id == workspace_id, Issue.status.in_(["done", "cancelled"])
    )
    res = await db.execute(
        update(InboxItem)
        .where(
            InboxItem.workspace_id == workspace_id,
            InboxItem.user_id == user_id,
            InboxItem.archived == False,  # noqa: E712
            InboxItem.issue_id.in_(done_ids),
        )
        .values(archived=True)
    )
    await db.commit()
    return res.rowcount or 0


async def unread_summary(db: AsyncSession, user_id: str) -> list[dict]:
    """Contagem de não lidos por workspace do usuário (badge do switcher)."""
    stmt = (
        select(InboxItem.workspace_id, func.count().label("count"))
        .join(
            Member,
            (Member.workspace_id == InboxItem.workspace_id) & (Member.user_id == InboxItem.user_id),
        )
        .where(
            InboxItem.user_id == user_id,
            InboxItem.read == False,  # noqa: E712
            InboxItem.archived == False,  # noqa: E712
        )
        .group_by(InboxItem.workspace_id)
    )
    rows = (await db.execute(stmt)).all()
    return [{"workspace_id": ws_id, "count": int(count)} for ws_id, count in rows]


# ── Usage ─────────────────────────────────────────────────────────────
async def usage_summary(db: AsyncSession, workspace_id: str, days: int = 30) -> dict:
    """Agrega AgentTask on-the-fly: tokens, custo e contagem por status,
    quebrado por dia e por agente, últimos `days` dias."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = select(AgentTask).where(
        AgentTask.workspace_id == workspace_id,
        AgentTask.created_at >= since,
    )
    tasks = list((await db.execute(stmt)).scalars())

    agents = list((await db.execute(select(Agent).where(Agent.workspace_id == workspace_id))).scalars())
    agent_names = {a.id: a.name for a in agents}

    def _bucket() -> dict:
        return {"tasks": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "by_status": {}}

    totals = _bucket()
    by_day: dict[str, dict] = {}
    by_agent: dict[str, dict] = {}

    for t in tasks:
        day = t.created_at.date().isoformat() if t.created_at else "unknown"
        for bucket in (totals, by_day.setdefault(day, _bucket()), by_agent.setdefault(t.agent_id, _bucket())):
            bucket["tasks"] += 1
            bucket["input_tokens"] += t.input_tokens or 0
            bucket["output_tokens"] += t.output_tokens or 0
            bucket["cost_usd"] += t.cost_usd or 0.0
            bucket["by_status"][t.status] = bucket["by_status"].get(t.status, 0) + 1

    for bucket in [totals, *by_day.values(), *by_agent.values()]:
        bucket["cost_usd"] = round(bucket["cost_usd"], 6)

    return {
        "workspace_id": workspace_id,
        "days": days,
        "since": since.isoformat(),
        "totals": totals,
        "by_day": [
            {"day": d, **b} for d, b in sorted(by_day.items(), reverse=True)
        ],
        "by_agent": [
            {"agent_id": aid, "agent_name": agent_names.get(aid, aid), **b}
            for aid, b in sorted(by_agent.items(), key=lambda kv: -kv[1]["cost_usd"])
        ],
    }
