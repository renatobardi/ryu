"""Serviço de PROPRIEDADES CUSTOMIZADAS de issue (paridade multica 191/196).

Modelo em duas partes:
1. issue_property — catálogo por workspace (definições tipadas; arquivar, nunca deletar).
2. issue.properties — bag JSON por issue keyed pelo id da definição; valores
   validados por tipo aqui no serviço; bag limitado a 16KB.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.models import Issue, IssueProperty, now
from ryu.realtime.hub import hub
from ryu.services.issues import IssueError, _log, get_issue, issue_to_dict

PROPERTY_TYPES = ["text", "number", "select", "multi_select", "date", "checkbox", "url"]
MAX_ACTIVE_PROPERTIES = 20
MAX_PROPERTIES_BAG_BYTES = 16 * 1024
MAX_TEXT_LEN = 4000
MAX_URL_LEN = 2048
POSITION_STEP = 1024.0


def property_to_dict(p: IssueProperty) -> dict:
    return {
        "id": p.id,
        "workspace_id": p.workspace_id,
        "name": p.name,
        "type": p.type,
        "description": p.description,
        "config": p.config or {},
        "icon": p.icon or "",
        "position": p.position,
        "archived_at": p.archived_at.isoformat() if p.archived_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _validate_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise IssueError("name é obrigatório")
    if len(name) > 100:
        raise IssueError("name muito longo (máx 100)")
    return name


def _validate_config(prop_type: str, config: dict | None) -> dict:
    """Canonicaliza o config. select/multi_select: {"options": [{id,name,color}]}."""
    if prop_type not in ("select", "multi_select"):
        return {}
    config = config or {}
    options = config.get("options") or []
    if not isinstance(options, list):
        raise IssueError("config.options deve ser uma lista")
    out = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for opt in options:
        if not isinstance(opt, dict):
            raise IssueError("cada option deve ser um objeto {id?, name, color?}")
        name = str(opt.get("name") or "").strip()
        if not name:
            raise IssueError("option.name é obrigatório")
        if name.lower() in seen_names:
            raise IssueError(f"option duplicada: {name}")
        seen_names.add(name.lower())
        oid = str(opt.get("id") or uuid.uuid4().hex)
        if oid in seen_ids:
            raise IssueError(f"option id duplicado: {oid}")
        seen_ids.add(oid)
        entry: dict = {"id": oid, "name": name}
        if opt.get("color"):
            entry["color"] = str(opt["color"])
        out.append(entry)
    return {"options": out}


def _option_ids(config: dict | None) -> set[str]:
    return {str(o.get("id")) for o in (config or {}).get("options", []) if isinstance(o, dict)}


async def _active_count(db: AsyncSession, workspace_id: str, exclude_id: str | None = None) -> int:
    stmt = select(func.count()).select_from(IssueProperty).where(
        IssueProperty.workspace_id == workspace_id, IssueProperty.archived_at.is_(None)
    )
    if exclude_id:
        stmt = stmt.where(IssueProperty.id != exclude_id)
    return int((await db.execute(stmt)).scalar_one())


# ── Catálogo ──────────────────────────────────────────────────────────
async def create_property(
    db: AsyncSession,
    workspace_id: str,
    actor_type: str,
    actor_id: str,
    *,
    name: str,
    type: str,
    description: str = "",
    config: dict | None = None,
    icon: str = "",
) -> IssueProperty:
    name = _validate_name(name)
    if type not in PROPERTY_TYPES:
        raise IssueError(f"type inválido: {type} (aceitos: {', '.join(PROPERTY_TYPES)})")
    if await _active_count(db, workspace_id) >= MAX_ACTIVE_PROPERTIES:
        raise IssueError(
            f"workspace não pode ter mais de {MAX_ACTIVE_PROPERTIES} propriedades ativas; arquive as não usadas"
        )
    maxpos = (
        await db.execute(
            select(func.max(IssueProperty.position)).where(IssueProperty.workspace_id == workspace_id)
        )
    ).scalar_one()
    prop = IssueProperty(
        workspace_id=workspace_id,
        name=name,
        type=type,
        description=description or "",
        config=_validate_config(type, config),
        icon=(icon or "")[:64],
        position=(maxpos or 0.0) + POSITION_STEP,
    )
    db.add(prop)
    await db.flush()
    await _log(db, workspace_id, actor_type, actor_id, "property_created", {"property_id": prop.id, "name": name})
    await db.commit()
    return prop


async def list_properties(
    db: AsyncSession, workspace_id: str, include_archived: bool = False
) -> list[IssueProperty]:
    stmt = select(IssueProperty).where(IssueProperty.workspace_id == workspace_id)
    if not include_archived:
        stmt = stmt.where(IssueProperty.archived_at.is_(None))
    stmt = stmt.order_by(IssueProperty.position)
    return list((await db.execute(stmt)).scalars())


async def get_property(db: AsyncSession, property_id: str) -> IssueProperty:
    prop = await db.get(IssueProperty, property_id)
    if prop is None:
        raise IssueError("propriedade não encontrada", 404)
    return prop


async def update_property(
    db: AsyncSession,
    property_id: str,
    actor_type: str,
    actor_id: str,
    changes: dict[str, Any],
) -> IssueProperty:
    """Aceita: name, description, config, icon, position, archived (bool).
    Definições são arquivadas, nunca deletadas; type é imutável."""
    prop = await get_property(db, property_id)
    if "type" in changes and changes["type"] != prop.type:
        raise IssueError("type de propriedade é imutável")
    if "name" in changes:
        prop.name = _validate_name(changes["name"])
    if "description" in changes:
        prop.description = changes["description"] or ""
    if "icon" in changes:
        prop.icon = (changes["icon"] or "")[:64]
    if "config" in changes:
        prop.config = _validate_config(prop.type, changes["config"])
    if "position" in changes and changes["position"] is not None:
        prop.position = float(changes["position"])
    if "archived" in changes:
        if changes["archived"] and prop.archived_at is None:
            prop.archived_at = now()
        elif not changes["archived"] and prop.archived_at is not None:
            if await _active_count(db, prop.workspace_id, exclude_id=prop.id) >= MAX_ACTIVE_PROPERTIES:
                raise IssueError(
                    f"workspace não pode ter mais de {MAX_ACTIVE_PROPERTIES} propriedades ativas"
                )
            prop.archived_at = None
    await _log(db, prop.workspace_id, actor_type, actor_id, "property_updated", {"property_id": prop.id})
    await db.commit()
    return prop


# ── Valores por issue ─────────────────────────────────────────────────
def _validate_value(prop: IssueProperty, value: Any) -> Any:
    t = prop.type
    if t == "text":
        if not isinstance(value, str):
            raise IssueError("valor de propriedade text deve ser string")
        if len(value) > MAX_TEXT_LEN:
            raise IssueError(f"texto excede {MAX_TEXT_LEN} caracteres")
        return value
    if t == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise IssueError("valor de propriedade number deve ser numérico")
        return value
    if t == "checkbox":
        if not isinstance(value, bool):
            raise IssueError("valor de propriedade checkbox deve ser boolean")
        return value
    if t == "url":
        if not isinstance(value, str) or not value.lower().startswith(("http://", "https://")):
            raise IssueError("valor de propriedade url deve começar com http:// ou https://")
        if len(value) > MAX_URL_LEN:
            raise IssueError(f"url excede {MAX_URL_LEN} caracteres")
        return value
    if t == "date":
        if not isinstance(value, str):
            raise IssueError("valor de propriedade date deve ser string ISO (YYYY-MM-DD)")
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise IssueError("data inválida; use formato ISO (YYYY-MM-DD)")
        return value
    if t == "select":
        if not isinstance(value, str):
            raise IssueError("valor de propriedade select deve ser o id de uma option")
        if value not in _option_ids(prop.config):
            raise IssueError(f"option desconhecida: {value}")
        return value
    if t == "multi_select":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise IssueError("valor de propriedade multi_select deve ser lista de ids de options")
        valid = _option_ids(prop.config)
        deduped: list[str] = []
        for v in value:
            if v not in valid:
                raise IssueError(f"option desconhecida: {v}")
            if v not in deduped:
                deduped.append(v)
        return deduped
    raise IssueError(f"type inválido: {t}")


async def set_issue_property(
    db: AsyncSession, issue_id: str, property_id: str, actor_type: str, actor_id: str, value: Any
) -> dict:
    issue = await get_issue(db, issue_id)
    prop = await get_property(db, property_id)
    if prop.workspace_id != issue.workspace_id:
        raise IssueError("propriedade de outro workspace", 404)
    if prop.archived_at is not None:
        raise IssueError("propriedade arquivada não aceita novos valores")
    if value is None:
        raise IssueError("value é obrigatório; para remover use DELETE")
    validated = _validate_value(prop, value)
    bag = dict(issue.properties or {})
    bag[property_id] = validated
    if len(json.dumps(bag)) > MAX_PROPERTIES_BAG_BYTES:
        raise IssueError(f"properties da issue excedem {MAX_PROPERTIES_BAG_BYTES} bytes")
    issue.properties = bag
    await _log(
        db, issue.workspace_id, actor_type, actor_id, "property_set",
        {"property_id": property_id, "value": validated}, issue.id,
    )
    await db.commit()
    await hub.publish(issue.workspace_id, "issue:updated", issue_to_dict(issue))
    return bag


async def delete_issue_property(
    db: AsyncSession, issue_id: str, property_id: str, actor_type: str, actor_id: str
) -> dict:
    issue = await get_issue(db, issue_id)
    bag = dict(issue.properties or {})
    if property_id in bag:
        bag.pop(property_id)
        issue.properties = bag
        await _log(
            db, issue.workspace_id, actor_type, actor_id, "property_unset",
            {"property_id": property_id}, issue.id,
        )
        await db.commit()
        await hub.publish(issue.workspace_id, "issue:updated", issue_to_dict(issue))
    return bag
