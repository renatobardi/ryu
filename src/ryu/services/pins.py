"""Serviço de PINNED ITEMS (issues/projects fixados por usuário — multica 038)."""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.models import Issue, PinnedItem, Project

POSITION_STEP = 1024.0
ITEM_TYPES = ("issue", "project")


class PinError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def pin_to_dict(p: PinnedItem, summary: dict | None = None) -> dict:
    d = {
        "id": p.id,
        "workspace_id": p.workspace_id,
        "user_id": p.user_id,
        "item_type": p.item_type,
        "item_id": p.item_id,
        "position": p.position,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
    if summary:
        d["item"] = summary
    return d


async def _item_summary(db: AsyncSession, item_type: str, item_id: str) -> dict | None:
    if item_type == "issue":
        issue = await db.get(Issue, item_id)
        if issue:
            return {"id": issue.id, "key": issue.key, "title": issue.title, "status": issue.status}
    elif item_type == "project":
        prj = await db.get(Project, item_id)
        if prj:
            return {"id": prj.id, "name": prj.name, "status": prj.status}
    return None


async def list_pins(db: AsyncSession, workspace_id: str, user_id: str) -> list[dict]:
    rows = await db.execute(
        select(PinnedItem)
        .where(PinnedItem.workspace_id == workspace_id, PinnedItem.user_id == user_id)
        .order_by(PinnedItem.position)
    )
    out = []
    for p in rows.scalars():
        out.append(pin_to_dict(p, await _item_summary(db, p.item_type, p.item_id)))
    return out


async def create_pin(
    db: AsyncSession, workspace_id: str, user_id: str, item_type: str, item_id: str
) -> PinnedItem:
    if item_type not in ITEM_TYPES:
        raise PinError(f"item_type inválido: {item_type} (issue|project)")
    if item_type == "issue":
        issue = await db.get(Issue, item_id)
        if issue is None or issue.workspace_id != workspace_id:
            raise PinError("issue não encontrada neste workspace", 404)
    else:
        prj = await db.get(Project, item_id)
        if prj is None or prj.workspace_id != workspace_id:
            raise PinError("project não encontrado neste workspace", 404)
    existing = await db.execute(
        select(PinnedItem).where(
            PinnedItem.workspace_id == workspace_id,
            PinnedItem.user_id == user_id,
            PinnedItem.item_type == item_type,
            PinnedItem.item_id == item_id,
        )
    )
    pin = existing.scalars().first()
    if pin is not None:
        return pin  # idempotente
    maxpos = (
        await db.execute(
            select(func.max(PinnedItem.position)).where(
                PinnedItem.workspace_id == workspace_id, PinnedItem.user_id == user_id
            )
        )
    ).scalar_one()
    pin = PinnedItem(
        workspace_id=workspace_id,
        user_id=user_id,
        item_type=item_type,
        item_id=item_id,
        position=(maxpos or 0.0) + POSITION_STEP,
    )
    db.add(pin)
    await db.commit()
    return pin


async def delete_pin(
    db: AsyncSession, workspace_id: str, user_id: str, item_type: str, item_id: str
) -> None:
    await db.execute(
        delete(PinnedItem).where(
            PinnedItem.workspace_id == workspace_id,
            PinnedItem.user_id == user_id,
            PinnedItem.item_type == item_type,
            PinnedItem.item_id == item_id,
        )
    )
    await db.commit()


async def reorder_pins(
    db: AsyncSession, workspace_id: str, user_id: str, items: list[dict]
) -> list[dict]:
    """Recebe a nova ordem: [{item_type, item_id}, ...]; reatribui positions."""
    rows = await db.execute(
        select(PinnedItem).where(
            PinnedItem.workspace_id == workspace_id, PinnedItem.user_id == user_id
        )
    )
    by_key = {(p.item_type, p.item_id): p for p in rows.scalars()}
    pos = POSITION_STEP
    for item in items:
        key = (item.get("item_type"), item.get("item_id"))
        pin = by_key.get(key)
        if pin is None:
            raise PinError(f"pin não encontrado: {key[0]}/{key[1]}", 404)
        pin.position = pos
        pos += POSITION_STEP
    await db.commit()
    return await list_pins(db, workspace_id, user_id)
