"""Serviço do domínio SKILLS + AUTOPILOTS + SQUADS.

- Skills: CRUD (markdown) + attach/detach em agents (AgentSkill).
- Autopilots: CRUD + execução (cron via APScheduler, webhook, manual).
  Cada run cria AutopilotRun + Issue a partir de `rule`, atribuída ao
  target_agent_id — o que enfileira AgentTask (status queued) pela mesma
  lógica do tracker (reuso de ryu.services.issues.create_issue).
- Squads: CRUD + membros; atribuir issue a squad cria AgentTask queued
  para o leader_agent_id com prompt de briefing pedindo delegação.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import re
import secrets
import zipfile
from datetime import datetime, timezone as _timezone
from pathlib import Path, PurePosixPath
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import SessionLocal
from ryu.models import (
    ActivityLog,
    Agent,
    AgentSkill,
    AgentTask,
    Autopilot,
    AutopilotCollaborator,
    AutopilotRuleVersion,
    AutopilotRun,
    AutopilotSubscriber,
    AutopilotTrigger,
    Issue,
    Label,
    Member,
    Skill,
    SkillFile,
    SkillLabel,
    Squad,
    SquadMember,
    User,
    WebhookDelivery,
    now,
)
from ryu.realtime.hub import hub
from ryu.services import issues as issues_svc

TRIGGER_TYPES = ["cron", "webhook", "manual"]
TRIGGER_KINDS = ("schedule", "webhook", "api")
TRIGGER_PROVIDERS = ("generic", "github")
AUTOPILOT_STATUSES = ("active", "paused", "archived")
EXECUTION_MODES = ("create_issue", "run_only")
IMPORT_CONFLICT_STRATEGIES = ("fail", "overwrite", "rename", "skip")


class AutomationError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ── serializers ───────────────────────────────────────────────────────
def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def skill_to_dict(s: Skill) -> dict:
    return {
        "id": s.id,
        "workspace_id": s.workspace_id,
        "name": s.name,
        "description": s.description,
        "content": s.content,
        "created_by": getattr(s, "created_by", None),
        "created_at": _iso(s.created_at),
        "updated_at": _iso(s.updated_at),
    }


def skill_file_to_dict(f: SkillFile) -> dict:
    return {
        "id": f.id,
        "skill_id": f.skill_id,
        "path": f.path,
        "content": f.content,
        "created_at": _iso(f.created_at),
        "updated_at": _iso(f.updated_at),
    }


def label_to_dict(lb: Label) -> dict:
    return {
        "id": lb.id,
        "workspace_id": lb.workspace_id,
        "name": lb.name,
        "color": lb.color,
        "resource_type": getattr(lb, "resource_type", "issue") or "issue",
        "description": getattr(lb, "description", "") or "",
    }


def autopilot_to_dict(a: Autopilot) -> dict:
    return {
        "id": a.id,
        "workspace_id": a.workspace_id,
        "name": a.name,
        "enabled": a.enabled,
        "status": getattr(a, "status", None) or ("active" if a.enabled else "paused"),
        "execution_mode": getattr(a, "execution_mode", None) or "create_issue",
        "issue_title_template": getattr(a, "issue_title_template", None),
        "trigger_type": a.trigger_type,
        "cron_expr": a.cron_expr,
        "webhook_token": a.webhook_token,
        "rule": a.rule,
        "target_agent_id": a.target_agent_id,
        "created_by_type": getattr(a, "created_by_type", None),
        "created_by_id": getattr(a, "created_by_id", None),
        "last_run_at": _iso(getattr(a, "last_run_at", None)),
        "created_at": _iso(a.created_at),
        "updated_at": _iso(a.updated_at),
    }


def trigger_to_dict(t: AutopilotTrigger) -> dict:
    return {
        "id": t.id,
        "autopilot_id": t.autopilot_id,
        "kind": t.kind,
        "enabled": t.enabled,
        "label": t.label,
        "cron_expression": t.cron_expression,
        "timezone": t.timezone,
        "webhook_token": t.webhook_token,
        "provider": t.provider,
        "has_signing_secret": bool(t.signing_secret),
        "event_filters": t.event_filters,
        "next_run_at": _iso(t.next_run_at),
        "last_fired_at": _iso(t.last_fired_at),
        "published_by_type": t.published_by_type,
        "published_by_id": t.published_by_id,
        "created_at": _iso(t.created_at),
        "updated_at": _iso(t.updated_at),
    }


def run_to_dict(r: AutopilotRun) -> dict:
    return {
        "id": r.id,
        "autopilot_id": r.autopilot_id,
        "status": r.status,
        "issue_id": r.issue_id,
        "detail": r.detail,
        "trigger_id": getattr(r, "trigger_id", None),
        "source": getattr(r, "source", None) or "manual",
        "task_id": getattr(r, "task_id", None),
        "completed_at": _iso(getattr(r, "completed_at", None)),
        "failure_reason": getattr(r, "failure_reason", None),
        "trigger_payload": getattr(r, "trigger_payload", None),
        "result": getattr(r, "result", None),
        "planned_at": _iso(getattr(r, "planned_at", None)),
        "rule_version_id": getattr(r, "rule_version_id", None),
        "created_at": _iso(r.created_at),
    }


def delivery_to_dict(d: WebhookDelivery, *, include_body: bool = False) -> dict:
    out = {
        "id": d.id,
        "workspace_id": d.workspace_id,
        "autopilot_id": d.autopilot_id,
        "trigger_id": d.trigger_id,
        "provider": d.provider,
        "event": d.event,
        "dedupe_key": d.dedupe_key,
        "dedupe_source": d.dedupe_source,
        "signature_status": d.signature_status,
        "status": d.status,
        "attempt_count": d.attempt_count,
        "selected_headers": d.selected_headers or {},
        "content_type": d.content_type,
        "response_status": d.response_status,
        "response_body": d.response_body,
        "autopilot_run_id": d.autopilot_run_id,
        "replayed_from_delivery_id": d.replayed_from_delivery_id,
        "error": d.error,
        "received_at": _iso(d.received_at),
        "last_attempt_at": _iso(d.last_attempt_at),
        "created_at": _iso(d.created_at),
    }
    if include_body:
        out["raw_body"] = d.raw_body
    return out


def rule_version_to_dict(v: AutopilotRuleVersion) -> dict:
    return {
        "id": v.id,
        "autopilot_id": v.autopilot_id,
        "workspace_id": v.workspace_id,
        "published_by_type": v.published_by_type,
        "published_by_id": v.published_by_id,
        "config_summary": v.config_summary or {},
        "created_at": _iso(v.created_at),
    }


def squad_to_dict(s: Squad, members: list[SquadMember] | None = None) -> dict:
    d = {
        "id": s.id,
        "workspace_id": s.workspace_id,
        "name": s.name,
        "leader_agent_id": s.leader_agent_id,
        "description": getattr(s, "description", "") or "",
        "instructions": getattr(s, "instructions", "") or "",
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }
    if members is not None:
        d["members"] = [
            {"member_type": m.member_type, "member_id": m.member_id, "role": getattr(m, "role", "") or ""}
            for m in members
        ]
    return d


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


async def _get_agent(db: AsyncSession, agent_id: str, workspace_id: str | None = None) -> Agent:
    agent = await db.get(Agent, agent_id)
    if agent is None or (workspace_id and agent.workspace_id != workspace_id):
        raise AutomationError("agent não encontrado", 404)
    return agent


# ═══════════════════════════ SKILLS ═══════════════════════════════════
async def _skill_by_name(db: AsyncSession, workspace_id: str, name: str) -> Skill | None:
    rows = await db.execute(
        select(Skill).where(Skill.workspace_id == workspace_id, Skill.name == name.strip())
    )
    return rows.scalars().first()


async def create_skill(
    db: AsyncSession,
    workspace_id: str,
    name: str,
    description: str = "",
    content: str = "",
    created_by: str | None = None,
) -> Skill:
    if not name.strip():
        raise AutomationError("name é obrigatório")
    # unicidade de nome por workspace (multica UNIQUE(workspace_id, name))
    if await _skill_by_name(db, workspace_id, name) is not None:
        raise AutomationError("já existe uma skill com este nome neste workspace", 409)
    skill = Skill(
        workspace_id=workspace_id,
        name=name.strip(),
        description=description or "",
        content=content or "",
        created_by=created_by,
    )
    db.add(skill)
    await db.commit()
    return skill


async def list_skills(
    db: AsyncSession, workspace_id: str, label_id: str | None = None
) -> list[Skill]:
    stmt = select(Skill).where(Skill.workspace_id == workspace_id).order_by(Skill.created_at)
    if label_id:
        stmt = (
            select(Skill)
            .join(SkillLabel, SkillLabel.skill_id == Skill.id)
            .where(Skill.workspace_id == workspace_id, SkillLabel.label_id == label_id)
            .order_by(Skill.created_at)
        )
    rows = await db.execute(stmt)
    return list(rows.scalars())


async def get_skill(db: AsyncSession, skill_id: str) -> Skill:
    skill = await db.get(Skill, skill_id)
    if skill is None:
        raise AutomationError("skill não encontrada", 404)
    return skill


async def update_skill(db: AsyncSession, skill_id: str, fields: dict[str, Any]) -> Skill:
    skill = await get_skill(db, skill_id)
    if fields.get("name") and fields["name"].strip() != skill.name:
        other = await _skill_by_name(db, skill.workspace_id, fields["name"])
        if other is not None and other.id != skill.id:
            raise AutomationError("já existe uma skill com este nome neste workspace", 409)
    for k in ("name", "description", "content"):
        if k in fields and fields[k] is not None:
            setattr(skill, k, fields[k])
    if not skill.name.strip():
        raise AutomationError("name é obrigatório")
    await db.commit()
    return skill


async def delete_skill(db: AsyncSession, skill_id: str) -> None:
    skill = await get_skill(db, skill_id)
    await db.execute(delete(AgentSkill).where(AgentSkill.skill_id == skill_id))
    await db.execute(delete(SkillFile).where(SkillFile.skill_id == skill_id))
    await db.execute(delete(SkillLabel).where(SkillLabel.skill_id == skill_id))
    await db.delete(skill)
    await db.commit()


async def attach_skill(db: AsyncSession, skill_id: str, agent_id: str) -> None:
    skill = await get_skill(db, skill_id)
    await _get_agent(db, agent_id, skill.workspace_id)
    existing = await db.execute(
        select(AgentSkill).where(AgentSkill.skill_id == skill_id, AgentSkill.agent_id == agent_id)
    )
    if existing.first() is None:
        db.add(AgentSkill(agent_id=agent_id, skill_id=skill_id))
        await db.commit()


async def detach_skill(db: AsyncSession, skill_id: str, agent_id: str) -> None:
    await db.execute(
        delete(AgentSkill).where(AgentSkill.skill_id == skill_id, AgentSkill.agent_id == agent_id)
    )
    await db.commit()


async def skills_for_agent(db: AsyncSession, agent_id: str) -> list[Skill]:
    rows = await db.execute(
        select(Skill).join(AgentSkill, AgentSkill.skill_id == Skill.id).where(AgentSkill.agent_id == agent_id)
    )
    return list(rows.scalars())


async def agents_for_skill(db: AsyncSession, skill_id: str) -> list[Agent]:
    rows = await db.execute(
        select(Agent).join(AgentSkill, AgentSkill.agent_id == Agent.id).where(AgentSkill.skill_id == skill_id)
    )
    return list(rows.scalars())


# ── Skill files (multica 008 skill_file) ──────────────────────────────
def _normalize_skill_path(path: str) -> str:
    """Path relativo POSIX seguro (sem raiz, sem `..`, sem vazio)."""
    p = (path or "").strip().replace("\\", "/").lstrip("/")
    parts = [seg for seg in PurePosixPath(p).parts if seg not in ("", ".")]
    if not parts or any(seg == ".." for seg in parts):
        raise AutomationError("path inválido")
    norm = "/".join(parts)
    if norm.lower() == "skill.md":
        raise AutomationError("SKILL.md é o conteúdo da própria skill — edite o campo content")
    return norm


async def list_skill_files(db: AsyncSession, skill_id: str) -> list[SkillFile]:
    await get_skill(db, skill_id)
    rows = await db.execute(
        select(SkillFile).where(SkillFile.skill_id == skill_id).order_by(SkillFile.path)
    )
    return list(rows.scalars())


async def upsert_skill_file(db: AsyncSession, skill_id: str, path: str, content: str) -> SkillFile:
    await get_skill(db, skill_id)
    norm = _normalize_skill_path(path)
    rows = await db.execute(
        select(SkillFile).where(SkillFile.skill_id == skill_id, SkillFile.path == norm)
    )
    f = rows.scalars().first()
    if f is None:
        f = SkillFile(skill_id=skill_id, path=norm, content=content or "")
        db.add(f)
    else:
        f.content = content or ""
    await db.commit()
    return f


async def delete_skill_file(db: AsyncSession, skill_id: str, file_id: str) -> None:
    rows = await db.execute(
        select(SkillFile).where(SkillFile.id == file_id, SkillFile.skill_id == skill_id)
    )
    f = rows.scalars().first()
    if f is None:
        raise AutomationError("arquivo não encontrado", 404)
    await db.delete(f)
    await db.commit()


# ── Skill labels (multica 162 resource_labels) ────────────────────────
async def list_labels_for_skill(db: AsyncSession, skill_id: str) -> list[Label]:
    await get_skill(db, skill_id)
    rows = await db.execute(
        select(Label).join(SkillLabel, SkillLabel.label_id == Label.id).where(SkillLabel.skill_id == skill_id)
    )
    return list(rows.scalars())


async def attach_label_to_skill(
    db: AsyncSession,
    skill_id: str,
    *,
    label_id: str | None = None,
    name: str | None = None,
    color: str | None = None,
) -> Label:
    skill = await get_skill(db, skill_id)
    label: Label | None = None
    if label_id:
        label = await db.get(Label, label_id)
        if label is None or label.workspace_id != skill.workspace_id:
            raise AutomationError("label não encontrada neste workspace", 404)
    elif name and name.strip():
        rows = await db.execute(
            select(Label).where(
                Label.workspace_id == skill.workspace_id,
                Label.name == name.strip(),
                Label.resource_type == "skill",
            )
        )
        label = rows.scalars().first()
        if label is None:
            label = Label(
                workspace_id=skill.workspace_id,
                name=name.strip(),
                color=color or "#8b5cf6",
                resource_type="skill",
            )
            db.add(label)
            await db.flush()
    else:
        raise AutomationError("label_id ou name é obrigatório")
    existing = await db.execute(
        select(SkillLabel).where(SkillLabel.skill_id == skill_id, SkillLabel.label_id == label.id)
    )
    if existing.scalars().first() is None:
        db.add(SkillLabel(skill_id=skill_id, label_id=label.id))
    await db.commit()
    return label


async def detach_label_from_skill(db: AsyncSession, skill_id: str, label_id: str) -> None:
    await db.execute(
        delete(SkillLabel).where(SkillLabel.skill_id == skill_id, SkillLabel.label_id == label_id)
    )
    await db.commit()


# ── Skill import (.md / .zip) — multica ImportSkill ───────────────────
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse_skill_markdown(text: str) -> tuple[str, str, str]:
    """Extrai (name, description, body) de um SKILL.md com frontmatter simples."""
    name, description = "", ""
    body = text
    m = _FRONTMATTER_RE.match(text)
    if m:
        body = text[m.end():]
        for line in m.group(1).splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip().strip("'\"")
            if key == "name":
                name = value
            elif key == "description":
                description = value
    return name, description, body.strip()


def _parse_skill_archive(data: bytes) -> tuple[str, str, str, list[tuple[str, str]]]:
    """Lê um .zip com SKILL.md + arquivos → (name, description, content, files)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise AutomationError("arquivo .zip inválido")
    names = [n for n in zf.namelist() if not n.endswith("/")]
    skill_md = None
    for n in names:
        if PurePosixPath(n).name.lower() == "skill.md":
            if skill_md is None or len(PurePosixPath(n).parts) < len(PurePosixPath(skill_md).parts):
                skill_md = n
    if skill_md is None:
        raise AutomationError("o .zip precisa conter um SKILL.md")
    root = str(PurePosixPath(skill_md).parent)
    prefix = "" if root in (".", "") else root + "/"
    try:
        text = zf.read(skill_md).decode("utf-8", errors="replace")
    except Exception:
        raise AutomationError("falha ao ler SKILL.md do arquivo")
    name, description, content = parse_skill_markdown(text)
    files: list[tuple[str, str]] = []
    for n in names:
        if n == skill_md:
            continue
        rel = n[len(prefix):] if prefix and n.startswith(prefix) else n
        base = PurePosixPath(rel).name
        if not rel or base.startswith(".") or base == "__MACOSX":
            continue
        info = zf.getinfo(n)
        if info.file_size > 1024 * 1024:
            raise AutomationError(f"arquivo {rel} excede 1MB")
        if len(files) >= 200:
            raise AutomationError("o .zip contém arquivos demais (cap 200)")
        try:
            rel = _normalize_skill_path(rel)
        except AutomationError:
            continue
        files.append((rel, zf.read(n).decode("utf-8", errors="replace")))
    return name, description, content, files


async def _unique_skill_name(db: AsyncSession, workspace_id: str, base: str) -> str:
    name = base
    i = 2
    while await _skill_by_name(db, workspace_id, name) is not None:
        name = f"{base} ({i})"
        i += 1
        if i > 100:
            raise AutomationError("não foi possível gerar nome único", 409)
    return name


async def import_skill(
    db: AsyncSession,
    workspace_id: str,
    *,
    filename: str,
    data: bytes,
    on_conflict: str = "fail",
    created_by: str | None = None,
) -> dict:
    """Importa uma skill de um .md único ou .zip (SKILL.md + arquivos).

    Estratégias de conflito por nome (multica ImportSkill):
    fail (409 estruturado) | overwrite | rename | skip.
    """
    if on_conflict not in IMPORT_CONFLICT_STRATEGIES:
        raise AutomationError(
            f"on_conflict deve ser um de: {', '.join(IMPORT_CONFLICT_STRATEGIES)}"
        )
    lower = (filename or "").lower()
    if lower.endswith(".zip") or (data[:4] == b"PK\x03\x04"):
        name, description, content, files = _parse_skill_archive(data)
        if not name:
            name = Path(filename).stem or "imported-skill"
    elif lower.endswith((".md", ".markdown")) or not lower:
        text = data.decode("utf-8", errors="replace")
        name, description, content = parse_skill_markdown(text)
        if not name:
            name = Path(filename).stem or "imported-skill"
        files = []
    else:
        raise AutomationError("formato não suportado — envie um .md ou um .zip")
    name = name.strip()
    if not name:
        raise AutomationError("não foi possível determinar o nome da skill")

    existing = await _skill_by_name(db, workspace_id, name)
    status = "created"
    if existing is not None:
        if on_conflict == "fail":
            raise AutomationError(
                json.dumps({
                    "status": "conflict",
                    "name": name,
                    "existing_skill_id": existing.id,
                    "hint": "use on_conflict=overwrite|rename|skip",
                }),
                409,
            )
        if on_conflict == "skip":
            return {"status": "skipped", "skill": skill_to_dict(existing)}
        if on_conflict == "rename":
            name = await _unique_skill_name(db, workspace_id, name)
            existing = None
            status = "created"
        else:  # overwrite
            status = "overwritten"

    if existing is not None:  # overwrite
        existing.description = description or ""
        existing.content = content or ""
        await db.execute(delete(SkillFile).where(SkillFile.skill_id == existing.id))
        skill = existing
    else:
        skill = Skill(
            workspace_id=workspace_id,
            name=name,
            description=description or "",
            content=content or "",
            created_by=created_by,
        )
        db.add(skill)
        await db.flush()
    for rel, text in files:
        db.add(SkillFile(skill_id=skill.id, path=rel, content=text))
    await db.commit()
    return {"status": status, "skill": skill_to_dict(skill), "files": len(files)}


# ── Skills locais do runtime (multica runtime_local_skills) ───────────
def _local_skills_roots() -> list[Path]:
    from ryu.config import settings

    if settings.local_skills_dir:
        return [Path(settings.local_skills_dir)]
    return [Path.home() / ".claude" / "skills"]


def scan_local_skills() -> list[dict]:
    """Varre o diretório de skills do runtime local (equivalente in-process do
    request assíncrono POST /api/runtimes/{id}/local-skills do multica)."""
    out: list[dict] = []
    for root in _local_skills_roots():
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            md = d / "SKILL.md"
            if not d.is_dir() or not md.is_file():
                continue
            try:
                name, description, _ = parse_skill_markdown(md.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            files = [
                str(p.relative_to(d))
                for p in d.rglob("*")
                if p.is_file() and p != md and not p.name.startswith(".")
            ]
            out.append({
                "dir_name": d.name,
                "name": name or d.name,
                "description": description,
                "path": str(d),
                "files": files[:100],
                "file_count": len(files),
            })
    return out


async def import_local_skill(
    db: AsyncSession,
    workspace_id: str,
    dir_name: str,
    *,
    on_conflict: str = "fail",
    created_by: str | None = None,
) -> dict:
    """Importa uma skill do filesystem do runtime local para o workspace."""
    if on_conflict not in IMPORT_CONFLICT_STRATEGIES:
        raise AutomationError(
            f"on_conflict deve ser um de: {', '.join(IMPORT_CONFLICT_STRATEGIES)}"
        )
    target: Path | None = None
    for root in _local_skills_roots():
        cand = root / dir_name
        if cand.is_dir() and (cand / "SKILL.md").is_file():
            target = cand
            break
    if target is None:
        raise AutomationError("skill local não encontrada", 404)
    name, description, content = parse_skill_markdown(
        (target / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    )
    name = name or dir_name
    # monta um zip em memória? não precisa — reusa o fluxo de conflito do import
    existing = await _skill_by_name(db, workspace_id, name)
    status = "created"
    if existing is not None:
        if on_conflict == "fail":
            raise AutomationError(
                json.dumps({"status": "conflict", "name": name, "existing_skill_id": existing.id}), 409
            )
        if on_conflict == "skip":
            return {"status": "skipped", "skill": skill_to_dict(existing)}
        if on_conflict == "rename":
            name = await _unique_skill_name(db, workspace_id, name)
            existing = None
        else:
            status = "overwritten"
    if existing is not None:
        existing.description = description or ""
        existing.content = content or ""
        await db.execute(delete(SkillFile).where(SkillFile.skill_id == existing.id))
        skill = existing
    else:
        skill = Skill(
            workspace_id=workspace_id,
            name=name,
            description=description or "",
            content=content or "",
            created_by=created_by,
        )
        db.add(skill)
        await db.flush()
    count = 0
    for p in sorted(target.rglob("*")):
        if not p.is_file() or p.name == "SKILL.md" or p.name.startswith("."):
            continue
        if p.stat().st_size > 1024 * 1024 or count >= 200:
            continue
        rel = str(p.relative_to(target))
        try:
            rel = _normalize_skill_path(rel)
        except AutomationError:
            continue
        db.add(SkillFile(skill_id=skill.id, path=rel, content=p.read_text(encoding="utf-8", errors="replace")))
        count += 1
    await db.commit()
    return {"status": status, "skill": skill_to_dict(skill), "files": count}


# ═══════════════════════════ AUTOPILOTS ═══════════════════════════════
# referência ao scheduler (setada em register_autopilot_jobs no lifespan)
_scheduler = None


def _mint_webhook_token() -> str:
    return f"awh_{secrets.token_urlsafe(24)}"


def _trig_job_id(trigger_id: str) -> str:
    return f"autopilot-trigger:{trigger_id}"


def _validate_cron(expr: str) -> None:
    from apscheduler.triggers.cron import CronTrigger

    try:
        CronTrigger.from_crontab(expr)
    except ValueError as e:
        raise AutomationError(f"cron_expr inválida: {e}")


def _validate_timezone(tz: str) -> str:
    tz = (tz or "UTC").strip() or "UTC"
    try:
        ZoneInfo(tz)
    except Exception:
        raise AutomationError(f"timezone inválido: {tz}")
    return tz


def _validate_event_filters(filters: Any) -> list | None:
    """[{"event": "workflow_run", "actions": ["completed"]}] — multica 110."""
    if filters is None:
        return None
    if not isinstance(filters, list):
        raise AutomationError("event_filters deve ser uma lista")
    out = []
    for f in filters:
        if not isinstance(f, dict) or not isinstance(f.get("event"), str) or not f["event"].strip():
            raise AutomationError("cada event_filter precisa de um campo 'event' string")
        actions = f.get("actions") or []
        if not isinstance(actions, list) or any(not isinstance(a, str) for a in actions):
            raise AutomationError("event_filter.actions deve ser lista de strings")
        out.append({"event": f["event"].strip(), "actions": [a.strip() for a in actions if a.strip()]})
    return out or None


def _schedule_trigger(trig: AutopilotTrigger, autopilot_enabled: bool) -> None:
    """(Re)agenda o job cron de um trigger schedule no scheduler global."""
    if _scheduler is None:
        return
    from apscheduler.triggers.cron import CronTrigger

    try:
        _scheduler.remove_job(_trig_job_id(trig.id))
    except Exception:
        pass
    if trig.kind == "schedule" and trig.enabled and trig.cron_expression and autopilot_enabled:
        try:
            cron = CronTrigger.from_crontab(trig.cron_expression, timezone=trig.timezone or "UTC")
        except Exception:
            return
        _scheduler.add_job(
            _cron_fire_trigger,
            cron,
            args=[trig.id],
            id=_trig_job_id(trig.id),
            replace_existing=True,
        )


def _unschedule_trigger(trigger_id: str) -> None:
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(_trig_job_id(trigger_id))
    except Exception:
        pass


def _reschedule_all(ap: Autopilot, triggers: list[AutopilotTrigger]) -> None:
    active = ap.enabled and (getattr(ap, "status", "active") or "active") == "active"
    for t in triggers:
        _schedule_trigger(t, active)


async def _cron_fire_trigger(trigger_id: str) -> None:
    """Executado pelo APScheduler — abre sessão própria. planned_at = minuto
    planejado do disparo, usado como guarda de idempotência (multica 124)."""
    async with SessionLocal() as db:
        trig = await db.get(AutopilotTrigger, trigger_id)
        if trig is None or not trig.enabled or trig.kind != "schedule":
            return
        ap = await db.get(Autopilot, trig.autopilot_id)
        if ap is None or not ap.enabled or (getattr(ap, "status", "active") or "active") != "active":
            return
        planned = now().replace(second=0, microsecond=0)
        try:
            await run_autopilot(
                db, ap, source="schedule", trigger=trig, planned_at=planned
            )
            trig.last_fired_at = now()
            await db.commit()
        except Exception:
            pass  # falha já registrada no AutopilotRun quando possível


async def _ensure_legacy_triggers(db: AsyncSession, ap: Autopilot) -> list[AutopilotTrigger]:
    """Sincroniza os campos legados (trigger_type/cron_expr/webhook_token)
    para linhas em autopilot_trigger. NÃO commita."""
    rows = await db.execute(
        select(AutopilotTrigger).where(AutopilotTrigger.autopilot_id == ap.id).order_by(AutopilotTrigger.created_at)
    )
    triggers = list(rows.scalars())
    if ap.trigger_type == "cron" and ap.cron_expr:
        sched = next((t for t in triggers if t.kind == "schedule"), None)
        if sched is None:
            sched = AutopilotTrigger(
                autopilot_id=ap.id,
                kind="schedule",
                cron_expression=ap.cron_expr,
                timezone="UTC",
                published_by_type=getattr(ap, "created_by_type", None),
                published_by_id=getattr(ap, "created_by_id", None),
            )
            db.add(sched)
            await db.flush()
            triggers.append(sched)
        elif sched.cron_expression != ap.cron_expr:
            sched.cron_expression = ap.cron_expr
    if ap.trigger_type == "webhook":
        wh = next((t for t in triggers if t.kind == "webhook"), None)
        if wh is None:
            if not ap.webhook_token:
                ap.webhook_token = _mint_webhook_token()
            wh = AutopilotTrigger(
                autopilot_id=ap.id,
                kind="webhook",
                webhook_token=ap.webhook_token,
                provider="generic",
                published_by_type=getattr(ap, "created_by_type", None),
                published_by_id=getattr(ap, "created_by_id", None),
            )
            db.add(wh)
            await db.flush()
            triggers.append(wh)
    return triggers


async def register_autopilot_jobs(scheduler) -> None:
    """Chamado pelo main no lifespan: agenda um job por trigger schedule
    habilitado (migra campos legados p/ autopilot_trigger na primeira carga)."""
    global _scheduler
    _scheduler = scheduler
    async with SessionLocal() as db:
        rows = await db.execute(select(Autopilot))
        autopilots = list(rows.scalars())
        for ap in autopilots:
            triggers = await _ensure_legacy_triggers(db, ap)
            _reschedule_all(ap, triggers)
        await db.commit()


# ── Permissões (multica memberCanWriteAutopilot / requireAutopilotWrite) ──
async def member_role(db: AsyncSession, workspace_id: str, user_id: str) -> str | None:
    rows = await db.execute(
        select(Member.role).where(Member.workspace_id == workspace_id, Member.user_id == user_id)
    )
    row = rows.first()
    return row[0] if row else None


async def can_write_autopilot(db: AsyncSession, ap: Autopilot, user_id: str) -> bool:
    """writer = criador ∪ owner/admin do workspace ∪ colaboradores."""
    role = await member_role(db, ap.workspace_id, user_id)
    if role is None:
        return False
    if role in ("owner", "admin"):
        return True
    created_type = getattr(ap, "created_by_type", None)
    created_id = getattr(ap, "created_by_id", None)
    # criador — ou autopilot legado sem criador registrado (qualquer membro)
    if created_id is None or (created_type in (None, "member") and created_id == user_id):
        return True
    rows = await db.execute(
        select(AutopilotCollaborator).where(
            AutopilotCollaborator.autopilot_id == ap.id,
            AutopilotCollaborator.user_type == "member",
            AutopilotCollaborator.user_id == user_id,
        )
    )
    return rows.scalars().first() is not None


async def require_autopilot_write(db: AsyncSession, ap: Autopilot, user: User) -> None:
    if not await can_write_autopilot(db, ap, user.id):
        raise AutomationError("sem permissão de escrita neste autopilot", 403)


async def require_autopilot_admin(db: AsyncSession, ap: Autopilot, user: User) -> None:
    """Gestão de colaboradores: restrita a criador/owner/admin."""
    role = await member_role(db, ap.workspace_id, user.id)
    if role in ("owner", "admin"):
        return
    if role is not None and getattr(ap, "created_by_id", None) in (None, user.id):
        return
    raise AutomationError("apenas criador/owner/admin gerenciam colaboradores", 403)


# ── Collaborators ─────────────────────────────────────────────────────
async def list_collaborators(db: AsyncSession, autopilot_id: str) -> list[AutopilotCollaborator]:
    rows = await db.execute(
        select(AutopilotCollaborator)
        .where(AutopilotCollaborator.autopilot_id == autopilot_id)
        .order_by(AutopilotCollaborator.created_at)
    )
    return list(rows.scalars())


async def add_collaborator(db: AsyncSession, ap: Autopilot, user_id: str, granted_by: str) -> None:
    if await member_role(db, ap.workspace_id, user_id) is None:
        raise AutomationError("usuário não é membro deste workspace", 404)
    rows = await db.execute(
        select(AutopilotCollaborator).where(
            AutopilotCollaborator.autopilot_id == ap.id,
            AutopilotCollaborator.user_type == "member",
            AutopilotCollaborator.user_id == user_id,
        )
    )
    if rows.scalars().first() is None:
        db.add(
            AutopilotCollaborator(
                autopilot_id=ap.id, user_type="member", user_id=user_id, granted_by=granted_by
            )
        )
    await db.commit()


async def remove_collaborator(db: AsyncSession, ap: Autopilot, user_id: str) -> None:
    await db.execute(
        delete(AutopilotCollaborator).where(
            AutopilotCollaborator.autopilot_id == ap.id,
            AutopilotCollaborator.user_type == "member",
            AutopilotCollaborator.user_id == user_id,
        )
    )
    await db.commit()


# ── Subscribers (multica 120_autopilot_subscriber) ────────────────────
async def list_autopilot_subscribers(db: AsyncSession, autopilot_id: str) -> list[str]:
    rows = await db.execute(
        select(AutopilotSubscriber.user_id)
        .where(AutopilotSubscriber.autopilot_id == autopilot_id, AutopilotSubscriber.user_type == "member")
        .order_by(AutopilotSubscriber.created_at)
    )
    return [uid for (uid,) in rows.all()]


async def set_autopilot_subscribers(db: AsyncSession, ap: Autopilot, user_ids: list[str]) -> None:
    """Substitui a lista de subscribers (validando membership). NÃO commita."""
    unique = list(dict.fromkeys(user_ids or []))
    for uid_ in unique:
        if await member_role(db, ap.workspace_id, uid_) is None:
            raise AutomationError(f"subscriber {uid_} não é membro deste workspace", 400)
    await db.execute(delete(AutopilotSubscriber).where(AutopilotSubscriber.autopilot_id == ap.id))
    for uid_ in unique:
        db.add(AutopilotSubscriber(autopilot_id=ap.id, user_type="member", user_id=uid_))


# ── Rule versions (multica 186 autopilot_rule_version) ────────────────
async def _config_summary(db: AsyncSession, ap: Autopilot) -> dict:
    rows = await db.execute(
        select(AutopilotTrigger).where(AutopilotTrigger.autopilot_id == ap.id).order_by(AutopilotTrigger.created_at)
    )
    return {
        "name": ap.name,
        "rule": (ap.rule or "")[:4000],
        "status": getattr(ap, "status", "active"),
        "execution_mode": getattr(ap, "execution_mode", "create_issue"),
        "issue_title_template": getattr(ap, "issue_title_template", None),
        "target_agent_id": ap.target_agent_id,
        "triggers": [
            {
                "id": t.id,
                "kind": t.kind,
                "enabled": t.enabled,
                "cron_expression": t.cron_expression,
                "timezone": t.timezone,
                "provider": t.provider,
                "event_filters": t.event_filters,
            }
            for t in rows.scalars()
        ],
    }


async def record_rule_version(
    db: AsyncSession, ap: Autopilot, actor_type: str, actor_id: str | None
) -> AutopilotRuleVersion:
    """Publicação substantiva → snapshot append-only. NÃO commita (flush)."""
    v = AutopilotRuleVersion(
        autopilot_id=ap.id,
        workspace_id=ap.workspace_id,
        published_by_type=actor_type or "system",
        published_by_id=actor_id,
        config_summary=await _config_summary(db, ap),
    )
    db.add(v)
    await db.flush()
    return v


async def latest_rule_version_id(db: AsyncSession, autopilot_id: str) -> str | None:
    rows = await db.execute(
        select(AutopilotRuleVersion.id)
        .where(AutopilotRuleVersion.autopilot_id == autopilot_id)
        .order_by(AutopilotRuleVersion.created_at.desc())
        .limit(1)
    )
    row = rows.first()
    return row[0] if row else None


async def list_rule_versions(db: AsyncSession, autopilot_id: str, limit: int = 50) -> list[AutopilotRuleVersion]:
    rows = await db.execute(
        select(AutopilotRuleVersion)
        .where(AutopilotRuleVersion.autopilot_id == autopilot_id)
        .order_by(AutopilotRuleVersion.created_at.desc())
        .limit(limit)
    )
    return list(rows.scalars())


async def create_autopilot(
    db: AsyncSession,
    workspace_id: str,
    *,
    name: str,
    rule: str,
    trigger_type: str = "cron",
    cron_expr: str | None = None,
    target_agent_id: str | None = None,
    enabled: bool = True,
    status: str | None = None,
    execution_mode: str = "create_issue",
    issue_title_template: str | None = None,
    subscribers: list[str] | None = None,
    triggers: list[dict] | None = None,
    created_by_type: str | None = None,
    created_by_id: str | None = None,
) -> Autopilot:
    if not name.strip():
        raise AutomationError("name é obrigatório")
    if trigger_type not in TRIGGER_TYPES:
        raise AutomationError(f"trigger_type inválido: {trigger_type}")
    if status is not None and status not in AUTOPILOT_STATUSES:
        raise AutomationError(f"status inválido: {status}")
    if execution_mode not in EXECUTION_MODES:
        raise AutomationError(f"execution_mode inválido: {execution_mode}")
    if trigger_type == "cron" and not triggers:
        if not cron_expr:
            raise AutomationError("cron_expr é obrigatório para trigger cron")
        _validate_cron(cron_expr)
    if target_agent_id:
        await _get_agent(db, target_agent_id, workspace_id)
    if execution_mode == "run_only" and not target_agent_id:
        raise AutomationError("execution_mode run_only exige target_agent_id")
    if status is None:
        status = "active" if enabled else "paused"
    ap = Autopilot(
        workspace_id=workspace_id,
        name=name.strip(),
        enabled=status == "active",
        status=status,
        execution_mode=execution_mode,
        issue_title_template=issue_title_template,
        trigger_type=trigger_type,
        cron_expr=cron_expr,
        webhook_token=_mint_webhook_token() if trigger_type == "webhook" else None,
        rule=rule or "",
        target_agent_id=target_agent_id,
        created_by_type=created_by_type,
        created_by_id=created_by_id,
    )
    db.add(ap)
    await db.flush()
    created_triggers: list[AutopilotTrigger] = []
    if triggers:
        for spec in triggers:
            created_triggers.append(
                await _build_trigger(db, ap, spec, created_by_type or "member", created_by_id)
            )
    else:
        created_triggers = await _ensure_legacy_triggers(db, ap)
    if subscribers:
        await set_autopilot_subscribers(db, ap, subscribers)
    await record_rule_version(db, ap, created_by_type or "system", created_by_id)
    await db.commit()
    _reschedule_all(ap, created_triggers)
    return ap


async def list_autopilots(db: AsyncSession, workspace_id: str) -> list[Autopilot]:
    rows = await db.execute(
        select(Autopilot).where(Autopilot.workspace_id == workspace_id).order_by(Autopilot.created_at)
    )
    return list(rows.scalars())


async def get_autopilot(db: AsyncSession, autopilot_id: str) -> Autopilot:
    ap = await db.get(Autopilot, autopilot_id)
    if ap is None:
        raise AutomationError("autopilot não encontrado", 404)
    return ap


async def get_autopilot_by_token(db: AsyncSession, webhook_token: str) -> Autopilot:
    rows = await db.execute(select(Autopilot).where(Autopilot.webhook_token == webhook_token))
    ap = rows.scalars().first()
    if ap is None:
        raise AutomationError("autopilot não encontrado", 404)
    return ap


_SUBSTANTIVE_FIELDS = ("rule", "target_agent_id", "execution_mode", "issue_title_template")


async def update_autopilot(
    db: AsyncSession,
    autopilot_id: str,
    fields: dict[str, Any],
    *,
    actor_type: str = "system",
    actor_id: str | None = None,
) -> Autopilot:
    ap = await get_autopilot(db, autopilot_id)
    substantive = False
    if "trigger_type" in fields and fields["trigger_type"] is not None:
        if fields["trigger_type"] not in TRIGGER_TYPES:
            raise AutomationError(f"trigger_type inválido: {fields['trigger_type']}")
        if ap.trigger_type != fields["trigger_type"]:
            substantive = True
        ap.trigger_type = fields["trigger_type"]
        if ap.trigger_type == "webhook" and not ap.webhook_token:
            ap.webhook_token = _mint_webhook_token()
    if "status" in fields and fields["status"] is not None:
        if fields["status"] not in AUTOPILOT_STATUSES:
            raise AutomationError(f"status inválido: {fields['status']}")
        if ap.status != fields["status"]:
            # enable/resume é publicação substantiva (multica 186)
            if fields["status"] == "active":
                substantive = True
            ap.status = fields["status"]
            ap.enabled = ap.status == "active"
    if "execution_mode" in fields and fields["execution_mode"] is not None:
        if fields["execution_mode"] not in EXECUTION_MODES:
            raise AutomationError(f"execution_mode inválido: {fields['execution_mode']}")
    for k in ("name", "rule", "cron_expr", "target_agent_id", "enabled",
              "execution_mode", "issue_title_template"):
        if k in fields and fields[k] is not None:
            if k in _SUBSTANTIVE_FIELDS and getattr(ap, k) != fields[k]:
                substantive = True
            if k == "cron_expr" and ap.cron_expr != fields[k]:
                substantive = True
            setattr(ap, k, fields[k])
    if "enabled" in fields and fields["enabled"] is not None:
        # espelha enabled → status (archived só muda via status explícito)
        if ap.status != "archived":
            new_status = "active" if ap.enabled else "paused"
            if new_status == "active" and ap.status != "active":
                substantive = True
            ap.status = new_status
    if ap.trigger_type == "cron":
        if not ap.cron_expr:
            raise AutomationError("cron_expr é obrigatório para trigger cron")
        _validate_cron(ap.cron_expr)
    if ap.target_agent_id:
        await _get_agent(db, ap.target_agent_id, ap.workspace_id)
    if getattr(ap, "execution_mode", "create_issue") == "run_only" and not ap.target_agent_id:
        raise AutomationError("execution_mode run_only exige target_agent_id")
    if "subscribers" in fields and fields["subscribers"] is not None:
        await set_autopilot_subscribers(db, ap, fields["subscribers"])
    triggers = await _ensure_legacy_triggers(db, ap)
    if substantive:
        await record_rule_version(db, ap, actor_type, actor_id)
        for t in triggers:
            t.published_by_type = actor_type if actor_type in ("member", "agent") else t.published_by_type
            t.published_by_id = actor_id if actor_type in ("member", "agent") else t.published_by_id
    await db.commit()
    _reschedule_all(ap, triggers)
    return ap


async def delete_autopilot(db: AsyncSession, autopilot_id: str) -> None:
    ap = await get_autopilot(db, autopilot_id)
    rows = await db.execute(select(AutopilotTrigger.id).where(AutopilotTrigger.autopilot_id == autopilot_id))
    trigger_ids = [tid for (tid,) in rows.all()]
    await db.execute(delete(AutopilotRun).where(AutopilotRun.autopilot_id == autopilot_id))
    await db.execute(delete(AutopilotTrigger).where(AutopilotTrigger.autopilot_id == autopilot_id))
    await db.execute(delete(WebhookDelivery).where(WebhookDelivery.autopilot_id == autopilot_id))
    await db.execute(delete(AutopilotCollaborator).where(AutopilotCollaborator.autopilot_id == autopilot_id))
    await db.execute(delete(AutopilotSubscriber).where(AutopilotSubscriber.autopilot_id == autopilot_id))
    await db.execute(delete(AutopilotRuleVersion).where(AutopilotRuleVersion.autopilot_id == autopilot_id))
    await db.delete(ap)
    await db.commit()
    for tid in trigger_ids:
        _unschedule_trigger(tid)


# ── Triggers CRUD (multica 042 autopilot_trigger) ─────────────────────
async def _build_trigger(
    db: AsyncSession, ap: Autopilot, spec: dict, actor_type: str, actor_id: str | None
) -> AutopilotTrigger:
    kind = spec.get("kind")
    if kind not in TRIGGER_KINDS:
        raise AutomationError(f"kind inválido: {kind} (aceitos: {', '.join(TRIGGER_KINDS)})")
    provider = spec.get("provider") or "generic"
    if provider not in TRIGGER_PROVIDERS:
        raise AutomationError(f"provider inválido: {provider}")
    cron_expression = spec.get("cron_expression")
    tz = _validate_timezone(spec.get("timezone") or "UTC")
    if kind == "schedule":
        if not cron_expression:
            raise AutomationError("cron_expression é obrigatório para kind schedule")
        _validate_cron(cron_expression)
    filters = _validate_event_filters(spec.get("event_filters"))
    trig = AutopilotTrigger(
        autopilot_id=ap.id,
        kind=kind,
        enabled=spec.get("enabled", True),
        label=spec.get("label") or "",
        cron_expression=cron_expression if kind == "schedule" else None,
        timezone=tz,
        webhook_token=_mint_webhook_token() if kind == "webhook" else None,
        provider=provider,
        signing_secret=spec.get("signing_secret") or None,
        event_filters=filters,
        published_by_type=actor_type if actor_type in ("member", "agent") else None,
        published_by_id=actor_id,
    )
    db.add(trig)
    await db.flush()
    return trig


async def list_triggers(db: AsyncSession, autopilot_id: str) -> list[AutopilotTrigger]:
    rows = await db.execute(
        select(AutopilotTrigger)
        .where(AutopilotTrigger.autopilot_id == autopilot_id)
        .order_by(AutopilotTrigger.created_at)
    )
    return list(rows.scalars())


async def get_trigger(db: AsyncSession, autopilot_id: str, trigger_id: str) -> AutopilotTrigger:
    trig = await db.get(AutopilotTrigger, trigger_id)
    if trig is None or trig.autopilot_id != autopilot_id:
        raise AutomationError("trigger não encontrado", 404)
    return trig


async def create_trigger(
    db: AsyncSession, ap: Autopilot, spec: dict, actor_type: str, actor_id: str | None
) -> AutopilotTrigger:
    trig = await _build_trigger(db, ap, spec, actor_type, actor_id)
    await record_rule_version(db, ap, actor_type, actor_id)
    await db.commit()
    _schedule_trigger(trig, ap.enabled and ap.status == "active")
    return trig


async def update_trigger(
    db: AsyncSession,
    ap: Autopilot,
    trigger_id: str,
    fields: dict[str, Any],
    actor_type: str,
    actor_id: str | None,
) -> AutopilotTrigger:
    trig = await get_trigger(db, ap.id, trigger_id)
    substantive = False
    if "cron_expression" in fields and fields["cron_expression"] is not None:
        if trig.kind != "schedule":
            raise AutomationError("cron_expression só se aplica a kind schedule")
        _validate_cron(fields["cron_expression"])
        substantive = substantive or trig.cron_expression != fields["cron_expression"]
        trig.cron_expression = fields["cron_expression"]
    if "timezone" in fields and fields["timezone"] is not None:
        tz = _validate_timezone(fields["timezone"])
        substantive = substantive or trig.timezone != tz
        trig.timezone = tz
    if "enabled" in fields and fields["enabled"] is not None:
        substantive = substantive or trig.enabled != bool(fields["enabled"])
        trig.enabled = bool(fields["enabled"])
    if "label" in fields and fields["label"] is not None:
        trig.label = fields["label"]
    if "provider" in fields and fields["provider"] is not None:
        if fields["provider"] not in TRIGGER_PROVIDERS:
            raise AutomationError(f"provider inválido: {fields['provider']}")
        trig.provider = fields["provider"]
    if "event_filters" in fields:
        filters = _validate_event_filters(fields["event_filters"])
        substantive = substantive or trig.event_filters != filters
        trig.event_filters = filters
    if substantive:
        trig.published_by_type = actor_type if actor_type in ("member", "agent") else trig.published_by_type
        trig.published_by_id = actor_id
        await record_rule_version(db, ap, actor_type, actor_id)
    await db.commit()
    _schedule_trigger(trig, ap.enabled and ap.status == "active")
    return trig


async def delete_trigger(
    db: AsyncSession, ap: Autopilot, trigger_id: str, actor_type: str, actor_id: str | None
) -> None:
    trig = await get_trigger(db, ap.id, trigger_id)
    await db.delete(trig)
    await record_rule_version(db, ap, actor_type, actor_id)
    await db.commit()
    _unschedule_trigger(trigger_id)


async def rotate_trigger_webhook_token(
    db: AsyncSession, ap: Autopilot, trigger_id: str, actor_type: str, actor_id: str | None
) -> AutopilotTrigger:
    """Minta novo token (invalida o antigo imediatamente) — multica
    RotateAutopilotTriggerWebhookToken."""
    trig = await get_trigger(db, ap.id, trigger_id)
    if trig.kind != "webhook":
        raise AutomationError("apenas triggers webhook têm token", 400)
    old = trig.webhook_token
    trig.webhook_token = _mint_webhook_token()
    trig.published_by_type = actor_type if actor_type in ("member", "agent") else trig.published_by_type
    trig.published_by_id = actor_id
    # espelha no campo legado se era o mesmo token
    if ap.webhook_token == old:
        ap.webhook_token = trig.webhook_token
    await db.commit()
    return trig


async def set_trigger_signing_secret(
    db: AsyncSession,
    ap: Autopilot,
    trigger_id: str,
    signing_secret: str | None,
    actor_type: str,
    actor_id: str | None,
) -> AutopilotTrigger:
    """Set/clear do signing secret HMAC (multica SetAutopilotTriggerSigningSecret)."""
    trig = await get_trigger(db, ap.id, trigger_id)
    if trig.kind != "webhook":
        raise AutomationError("apenas triggers webhook têm signing secret", 400)
    secret = (signing_secret or "").strip()
    if secret and len(secret) < 8:
        raise AutomationError("signing_secret deve ter pelo menos 8 caracteres")
    trig.signing_secret = secret or None
    trig.published_by_type = actor_type if actor_type in ("member", "agent") else trig.published_by_type
    trig.published_by_id = actor_id
    await db.commit()
    return trig


async def get_webhook_trigger_by_token(
    db: AsyncSession, token: str
) -> tuple[Autopilot, AutopilotTrigger] | None:
    rows = await db.execute(
        select(AutopilotTrigger).where(AutopilotTrigger.webhook_token == token)
    )
    trig = rows.scalars().first()
    if trig is not None:
        ap = await db.get(Autopilot, trig.autopilot_id)
        if ap is None:
            return None
        return ap, trig
    # legado: token no próprio autopilot sem linha de trigger
    rows = await db.execute(select(Autopilot).where(Autopilot.webhook_token == token))
    ap = rows.scalars().first()
    if ap is None:
        return None
    triggers = await _ensure_legacy_triggers(db, ap)
    await db.commit()
    trig = next((t for t in triggers if t.kind == "webhook"), None)
    if trig is None:
        return None
    return ap, trig


# ── Runs ──────────────────────────────────────────────────────────────
async def list_runs(db: AsyncSession, autopilot_id: str, limit: int = 50) -> list[AutopilotRun]:
    rows = await db.execute(
        select(AutopilotRun)
        .where(AutopilotRun.autopilot_id == autopilot_id)
        .order_by(AutopilotRun.created_at.desc())
        .limit(limit)
    )
    return list(rows.scalars())


async def get_run(db: AsyncSession, autopilot_id: str, run_id: str) -> AutopilotRun:
    run = await db.get(AutopilotRun, run_id)
    if run is None or run.autopilot_id != autopilot_id:
        raise AutomationError("run não encontrada", 404)
    return run


def _render_issue_title(ap: Autopilot, source: str, payload: dict | None) -> str:
    """issue_title_template com variáveis {name} {date} {time} {datetime} {event} {source}."""
    template = getattr(ap, "issue_title_template", None) or "[Autopilot] {name} — {date} {time}"
    ts = now()
    values = {
        "name": ap.name,
        "date": ts.strftime("%Y-%m-%d"),
        "time": ts.strftime("%H:%M"),
        "datetime": ts.strftime("%Y-%m-%d %H:%M"),
        "event": (payload or {}).get("event", "") if isinstance(payload, dict) else "",
        "source": source,
    }

    class _Safe(dict):
        def __missing__(self, key):  # noqa: D105
            return "{" + key + "}"

    try:
        title = template.format_map(_Safe(values)).strip()
    except Exception:
        title = f"[Autopilot] {ap.name} — {values['datetime']}"
    return title or f"[Autopilot] {ap.name} — {values['datetime']}"


def _payload_section(payload: dict | None) -> str:
    if not payload:
        return ""
    from ryu.config import settings

    try:
        dumped = json.dumps(payload, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        dumped = str(payload)
    cap = settings.webhook_payload_prompt_max_chars
    if len(dumped) > cap:
        dumped = dumped[:cap] + "\n… (payload truncado)"
    event = payload.get("event") if isinstance(payload, dict) else None
    head = f"\n\n## Evento disparador\nEvento: {event or 'webhook.received'}\n\n```json\n"
    return head + dumped + "\n```"


async def _notify_autopilot_subscribers(
    db: AsyncSession, ap: Autopilot, issue: Issue
) -> None:
    """Auto-inscreve subscribers na issue criada + item de inbox (multica
    notifyAutopilotSubscribersOnCreate). Best-effort, NÃO derruba o dispatch."""
    from ryu.services.inbox import notify

    for uid_ in await list_autopilot_subscribers(db, ap.id):
        try:
            await issues_svc.subscribe(db, issue.id, "member", uid_, reason="autopilot")
        except Exception:
            continue
    await db.commit()
    for uid_ in await list_autopilot_subscribers(db, ap.id):
        try:
            await notify(
                db,
                ap.workspace_id,
                uid_,
                "info",
                f"Autopilot '{ap.name}' criou {issue.key}",
                issue.title,
                issue_id=issue.id,
            )
        except Exception:
            continue


async def run_autopilot(
    db: AsyncSession,
    ap: Autopilot,
    source: str = "manual",
    *,
    trigger: AutopilotTrigger | None = None,
    payload: dict | None = None,
    planned_at: datetime | None = None,
) -> AutopilotRun:
    """Dispatch de um autopilot (multica DispatchAutopilot).

    - create_issue: cria AutopilotRun + Issue (título via template, payload no
      corpo), atribuída ao target_agent_id → enfileira AgentTask via tracker.
    - run_only: enfileira AgentTask direto (sem issue).
    - planned_at + trigger → guarda de idempotência (não duplica run do mesmo
      horário planejado — multica 124).
    - status archived nunca dispara (409); target indisponível → run skipped.
    """
    if (getattr(ap, "status", "active") or "active") == "archived":
        raise AutomationError("autopilot arquivado não dispara", 409)
    if source == "cron":
        source = "schedule"  # nome canônico multica
    if trigger is not None and planned_at is not None:
        rows = await db.execute(
            select(AutopilotRun).where(
                AutopilotRun.trigger_id == trigger.id, AutopilotRun.planned_at == planned_at
            )
        )
        existing = rows.scalars().first()
        if existing is not None:
            return existing  # dispatch idempotente

    run = AutopilotRun(
        autopilot_id=ap.id,
        status="running",
        detail=f"trigger: {source}",
        trigger_id=trigger.id if trigger is not None else None,
        source=source,
        trigger_payload=payload,
        planned_at=planned_at,
        rule_version_id=await latest_rule_version_id(db, ap.id),
    )
    db.add(run)
    try:
        await db.commit()
    except Exception:
        # corrida no unique (trigger_id, planned_at) — devolve a run vencedora
        await db.rollback()
        if trigger is not None and planned_at is not None:
            rows = await db.execute(
                select(AutopilotRun).where(
                    AutopilotRun.trigger_id == trigger.id, AutopilotRun.planned_at == planned_at
                )
            )
            existing = rows.scalars().first()
            if existing is not None:
                return existing
        raise

    execution_mode = getattr(ap, "execution_mode", "create_issue") or "create_issue"
    try:
        agent = None
        if ap.target_agent_id:
            agent = await db.get(Agent, ap.target_agent_id)
            if agent is not None and getattr(agent, "archived_at", None) is not None:
                agent = None
        if execution_mode == "run_only":
            if agent is None:
                run.status = "skipped"
                run.failure_reason = "agent_unavailable"
                run.completed_at = now()
                run.detail = f"trigger: {source}; skipped: target agent indisponível"
                await db.commit()
            else:
                prompt = (ap.rule or "") + _payload_section(payload)
                task = AgentTask(
                    workspace_id=ap.workspace_id,
                    agent_id=agent.id,
                    kind="issue",
                    status="queued",
                    prompt=prompt,
                )
                db.add(task)
                await db.flush()
                run.status = "done"
                run.task_id = task.id
                run.completed_at = now()
                run.result = {"task_id": task.id}
                run.detail = f"trigger: {source}; task {task.id} enfileirada (run_only)"
                ap.last_run_at = now()
                await _log(
                    db, ap.workspace_id, "system", f"autopilot:{ap.id}", "autopilot_run",
                    {"run_id": run.id, "source": source, "task_id": task.id},
                )
                await db.commit()
                await hub.publish(
                    ap.workspace_id,
                    "task:queued",
                    {"task_id": task.id, "agent_id": agent.id, "issue_id": None, "kind": "issue"},
                )
        else:
            title = _render_issue_title(ap, source, payload)
            has_agent = agent is not None
            description = (ap.rule or "") + _payload_section(payload)
            issue = await issues_svc.create_issue(
                db,
                ap.workspace_id,
                "system",
                f"autopilot:{ap.id}",
                title=title,
                description=description,
                status="todo" if has_agent else "backlog",
                assignee_type="agent" if has_agent else None,
                assignee_id=agent.id if has_agent else None,
            )
            run.status = "done"
            run.issue_id = issue.id
            run.completed_at = now()
            run.result = {"issue_id": issue.id, "issue_key": issue.key}
            run.detail = f"trigger: {source}; issue {issue.key}"
            ap.last_run_at = now()
            await _log(
                db,
                ap.workspace_id,
                "system",
                f"autopilot:{ap.id}",
                "autopilot_run",
                {"run_id": run.id, "source": source, "issue_key": issue.key},
                issue_id=issue.id,
            )
            await db.commit()
            try:
                await _notify_autopilot_subscribers(db, ap, issue)
            except Exception:
                pass
    except Exception as e:  # registra falha na run
        run.status = "failed"
        run.failure_reason = "dispatch_error"
        run.completed_at = now()
        run.detail = f"trigger: {source}; erro: {e}"
        await db.commit()

    await hub.publish(
        ap.workspace_id,
        "autopilot:run_done",
        {
            "autopilot_id": ap.id,
            "run_id": run.id,
            "status": run.status,
            "issue_id": run.issue_id,
            "task_id": getattr(run, "task_id", None),
            "source": source,
        },
    )
    return run


# ═══════════════ WEBHOOK INGRESS + DELIVERIES (multica 093) ═══════════
SIG_NOT_REQUIRED = "not_required"
SIG_VALID = "valid"
SIG_INVALID = "invalid"
SIG_MISSING = "missing"

_KNOWN_EVENT_PROVIDERS = ("github", "gitlab")


def _strip_bom(b: bytes) -> bytes:
    return b[3:] if b[:3] == b"\xef\xbb\xbf" else b


def normalize_webhook_payload(body: bytes, headers: dict[str, str]) -> dict:
    """Normaliza o corpo num envelope {event, eventPayload, request} (multica
    normalizeWebhookPayload). Levanta AutomationError(400) p/ JSON inválido."""
    body = _strip_bom(body)
    if not body.strip():
        raise AutomationError("empty body")
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError) as e:
        raise AutomationError(f"invalid json: {e}")
    if not isinstance(parsed, (dict, list)):
        raise AutomationError("body must be a JSON object or array")
    content_type = (headers.get("content-type") or "").split(";")[0].strip()
    env: dict[str, Any] = {
        "request": {
            "receivedAt": datetime.now(_timezone.utc).isoformat(),
            "contentType": content_type,
        }
    }
    if isinstance(parsed, dict) and isinstance(parsed.get("event"), str) and parsed["event"]:
        env["event"] = parsed["event"]
        env["eventPayload"] = parsed.get("eventPayload", parsed)
        return env
    env["event"] = _infer_event(headers, parsed)
    env["eventPayload"] = parsed
    return env


def _infer_event(headers: dict[str, str], body: Any) -> str:
    gh = headers.get("x-github-event", "")
    if gh:
        if isinstance(body, dict) and isinstance(body.get("action"), str) and body["action"]:
            return f"github.{gh}.{body['action']}"
        return f"github.{gh}"
    gl = headers.get("x-gitlab-event", "")
    if gl:
        return f"gitlab.{gl}"
    xe = headers.get("x-event-type", "")
    if xe:
        return xe
    if isinstance(body, dict):
        for key in ("event", "type", "action"):
            v = body.get(key)
            if isinstance(v, str) and v:
                return v
    return "webhook.received"


def extract_dedupe_key(provider: str, headers: dict[str, str]) -> tuple[str | None, str | None]:
    ghd = (headers.get("x-github-delivery") or "").strip()
    if ghd and provider == "github":
        return ghd, "x-github-delivery"
    idem = (headers.get("idempotency-key") or "").strip()
    if idem:
        return idem, "idempotency-key"
    if ghd:
        return ghd, "x-github-delivery"
    return None, None


def verify_webhook_signature(secret: str | None, headers: dict[str, str], body: bytes) -> str:
    """HMAC-SHA256 estilo GitHub: X-Hub-Signature-256: sha256=<hex>."""
    if not secret:
        return SIG_NOT_REQUIRED
    sig = headers.get("x-hub-signature-256", "")
    if not sig:
        return SIG_MISSING
    if not sig.startswith("sha256="):
        return SIG_INVALID
    want = sig[len("sha256="):]
    mac = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return SIG_VALID if hmac.compare_digest(mac, want) else SIG_INVALID


def selected_headers(headers: dict[str, str]) -> dict:
    """Subset de headers p/ debugging — nunca tokens/assinaturas em claro."""
    out: dict[str, Any] = {}
    for name in ("user-agent", "x-github-event", "x-github-delivery",
                 "x-gitlab-event", "x-event-type", "idempotency-key"):
        if headers.get(name):
            out[name] = headers[name]
    if headers.get("x-hub-signature-256"):
        out["x-hub-signature-256-present"] = True
    return out


def _split_webhook_event(event: str) -> tuple[str, str, str]:
    parts = (event or "").split(".")
    if parts and parts[0] in _KNOWN_EVENT_PROVIDERS:
        if len(parts) >= 3:
            return parts[0], parts[1], ".".join(parts[2:])
        if len(parts) == 2:
            return parts[0], parts[1], ""
        return parts[0], "", ""
    if len(parts) >= 2:
        return "", parts[0], ".".join(parts[1:])
    return "", event, ""


def event_allowed_by_filters(event_filters: list | None, envelope: dict) -> bool:
    """Filtros de evento do trigger (multica webhookEventAllowedByTriggerScope)."""
    if not event_filters:
        return True
    _, name, action = _split_webhook_event(envelope.get("event", ""))
    candidates = {action} if action else set()
    payload = envelope.get("eventPayload")
    if isinstance(payload, dict) and isinstance(payload.get("action"), str):
        candidates.add(payload["action"])
    for f in event_filters:
        if not isinstance(f, dict) or f.get("event") != name:
            continue
        allowed = f.get("actions") or []
        if not allowed:
            return True
        if any(a in allowed for a in candidates):
            return True
        # não retorna False aqui: outros filtros com o mesmo event ainda contam
    return False


async def list_deliveries(
    db: AsyncSession, autopilot_id: str, limit: int = 50, status: str | None = None
) -> list[WebhookDelivery]:
    stmt = (
        select(WebhookDelivery)
        .where(WebhookDelivery.autopilot_id == autopilot_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(WebhookDelivery.status == status)
    rows = await db.execute(stmt)
    return list(rows.scalars())


async def get_delivery(db: AsyncSession, autopilot_id: str, delivery_id: str) -> WebhookDelivery:
    d = await db.get(WebhookDelivery, delivery_id)
    if d is None or d.autopilot_id != autopilot_id:
        raise AutomationError("delivery não encontrada", 404)
    return d


async def _finalize_delivery(
    db: AsyncSession,
    delivery: WebhookDelivery,
    status: str,
    response_status: int,
    response_body: dict,
    error: str = "",
) -> None:
    delivery.status = status
    delivery.response_status = response_status
    delivery.response_body = json.dumps(response_body, ensure_ascii=False)[:4000]
    delivery.error = error
    delivery.last_attempt_at = now()
    await db.commit()


async def webhook_ingress(
    db: AsyncSession, token: str, *, body: bytes, headers: dict[str, str]
) -> tuple[int, dict]:
    """Fluxo persist-first do ingress público (multica HandleAutopilotWebhook).

    Retorna (status_code, response_body). Regras:
    413 corpo acima do cap; 404 token; 400 JSON inválido (sem persistência);
    duplicata → bump attempt_count; assinatura inválida/ausente → rejected 401;
    trigger desabilitado / paused / archived / event filtrado → ignored 200;
    senão dispatch → dispatched 200.
    """
    from ryu.config import settings

    headers = {k.lower(): v for k, v in headers.items()}
    if len(body) > settings.webhook_body_max_bytes:
        return 413, {"error": "payload too large"}
    pair = await get_webhook_trigger_by_token(db, token)
    if pair is None:
        return 404, {"error": "webhook not found"}
    ap, trig = pair
    try:
        envelope = normalize_webhook_payload(body, headers)
    except AutomationError as e:
        return 400, {"error": e.message}

    provider = trig.provider or "generic"
    dedupe_key, dedupe_source = extract_dedupe_key(provider, headers)
    sig_status = verify_webhook_signature(trig.signing_secret, headers, body)

    # dedupe: linha existente não-rejeitada/failed com a mesma chave → bump
    if dedupe_key:
        rows = await db.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.trigger_id == trig.id,
                WebhookDelivery.dedupe_key == dedupe_key,
                WebhookDelivery.status.notin_(("rejected", "failed")),
            )
        )
        existing = rows.scalars().first()
        if existing is not None:
            existing.attempt_count = (existing.attempt_count or 1) + 1
            existing.last_attempt_at = now()
            await db.commit()
            resp = {"status": "duplicate", "delivery_id": existing.id}
            if existing.autopilot_run_id:
                resp["run_id"] = existing.autopilot_run_id
            return 200, resp

    delivery = WebhookDelivery(
        workspace_id=ap.workspace_id,
        autopilot_id=ap.id,
        trigger_id=trig.id,
        provider=provider,
        event=envelope.get("event", "webhook.received"),
        dedupe_key=dedupe_key,
        dedupe_source=dedupe_source,
        signature_status=sig_status,
        content_type=envelope["request"].get("contentType") or None,
        raw_body=body.decode("utf-8", errors="replace")[: settings.webhook_body_max_bytes],
        selected_headers=selected_headers(headers),
    )
    db.add(delivery)
    await db.commit()

    if sig_status in (SIG_INVALID, SIG_MISSING):
        reason = "invalid_signature" if sig_status == SIG_INVALID else "missing_signature"
        resp = {"status": "rejected", "delivery_id": delivery.id, "reason": reason}
        await _finalize_delivery(db, delivery, "rejected", 401, resp, reason)
        return 401, resp

    def _ignored(reason: str) -> dict:
        return {"status": "ignored", "delivery_id": delivery.id, "reason": reason}

    if not trig.enabled:
        resp = _ignored("trigger_disabled")
        await _finalize_delivery(db, delivery, "ignored", 200, resp, "trigger_disabled")
        return 200, resp
    ap_status = getattr(ap, "status", "active") or "active"
    if ap_status == "archived":
        resp = _ignored("autopilot_archived")
        await _finalize_delivery(db, delivery, "ignored", 200, resp, "autopilot_archived")
        return 200, resp
    if ap_status != "active" or not ap.enabled:
        resp = _ignored("autopilot_paused")
        await _finalize_delivery(db, delivery, "ignored", 200, resp, "autopilot_paused")
        return 200, resp
    if not event_allowed_by_filters(trig.event_filters, envelope):
        resp = _ignored("event_filtered")
        resp["event"] = envelope.get("event")
        await _finalize_delivery(db, delivery, "ignored", 200, resp, "event_filtered")
        return 200, resp

    try:
        run = await run_autopilot(db, ap, source="webhook", trigger=trig, payload=envelope)
    except Exception as e:  # noqa: BLE001
        resp = {"status": "failed", "delivery_id": delivery.id, "error": str(e)[:500]}
        await _finalize_delivery(db, delivery, "failed", 500, resp, str(e)[:2000])
        return 500, resp
    trig.last_fired_at = now()
    delivery.autopilot_run_id = run.id
    resp = {
        "status": "accepted" if run.status != "skipped" else "skipped",
        "delivery_id": delivery.id,
        "run_id": run.id,
        "autopilot_id": ap.id,
        "trigger_id": trig.id,
    }
    if run.status == "skipped":
        resp["reason"] = run.failure_reason
    await _finalize_delivery(db, delivery, "dispatched", 200, resp)
    return 200, resp


async def replay_delivery(
    db: AsyncSession, ap: Autopilot, delivery_id: str
) -> tuple[WebhookDelivery, AutopilotRun | None]:
    """Recria a delivery a partir do corpo armazenado e redispara (multica
    ReplayAutopilotDelivery). A nova linha aponta replayed_from_delivery_id."""
    original = await get_delivery(db, ap.id, delivery_id)
    if not (original.raw_body or "").strip():
        raise AutomationError("delivery sem corpo armazenado — nada a redisparar", 409)
    trig = await db.get(AutopilotTrigger, original.trigger_id)
    if trig is None:
        raise AutomationError("trigger da delivery não existe mais", 409)
    ap_status = getattr(ap, "status", "active") or "active"
    if ap_status == "archived":
        raise AutomationError("autopilot arquivado não dispara", 409)
    body = original.raw_body.encode("utf-8")
    headers = {"content-type": original.content_type or "application/json"}
    try:
        envelope = normalize_webhook_payload(body, headers)
    except AutomationError:
        # corpo antigo pode ter sido um envelope já normalizado — reusa
        envelope = {"event": original.event, "eventPayload": None, "request": {}}
    replay = WebhookDelivery(
        workspace_id=ap.workspace_id,
        autopilot_id=ap.id,
        trigger_id=trig.id,
        provider=original.provider,
        event=original.event,
        signature_status=SIG_NOT_REQUIRED,  # replay é autenticado pela sessão
        content_type=original.content_type,
        raw_body=original.raw_body,
        selected_headers=original.selected_headers or {},
        replayed_from_delivery_id=original.id,
    )
    db.add(replay)
    await db.commit()
    if ap_status != "active" or not ap.enabled:
        resp = {"status": "ignored", "delivery_id": replay.id, "reason": "autopilot_paused"}
        await _finalize_delivery(db, replay, "ignored", 200, resp, "autopilot_paused")
        return replay, None
    try:
        run = await run_autopilot(db, ap, source="webhook", trigger=trig, payload=envelope)
    except Exception as e:  # noqa: BLE001
        resp = {"status": "failed", "delivery_id": replay.id, "error": str(e)[:500]}
        await _finalize_delivery(db, replay, "failed", 500, resp, str(e)[:2000])
        return replay, None
    replay.autopilot_run_id = run.id
    resp = {"status": "accepted", "delivery_id": replay.id, "run_id": run.id}
    await _finalize_delivery(db, replay, "dispatched", 200, resp)
    return replay, run


# ═══════════════════════════ SQUADS ═══════════════════════════════════
async def create_squad(
    db: AsyncSession,
    workspace_id: str,
    name: str,
    leader_agent_id: str,
    description: str = "",
    instructions: str = "",
) -> Squad:
    if not name.strip():
        raise AutomationError("name é obrigatório")
    await _get_agent(db, leader_agent_id, workspace_id)
    squad = Squad(
        workspace_id=workspace_id,
        name=name.strip(),
        leader_agent_id=leader_agent_id,
        description=description or "",
        instructions=instructions or "",
    )
    db.add(squad)
    await db.flush()
    # líder entra como membro automaticamente
    db.add(SquadMember(squad_id=squad.id, member_type="agent", member_id=leader_agent_id, role="leader"))
    await db.commit()
    return squad


async def list_squads(db: AsyncSession, workspace_id: str) -> list[Squad]:
    rows = await db.execute(
        select(Squad).where(Squad.workspace_id == workspace_id).order_by(Squad.created_at)
    )
    return list(rows.scalars())


async def get_squad(db: AsyncSession, squad_id: str) -> Squad:
    squad = await db.get(Squad, squad_id)
    if squad is None:
        raise AutomationError("squad não encontrada", 404)
    return squad


async def update_squad(db: AsyncSession, squad_id: str, fields: dict[str, Any]) -> Squad:
    squad = await get_squad(db, squad_id)
    if "name" in fields and fields["name"] is not None:
        squad.name = fields["name"]
    if "description" in fields and fields["description"] is not None:
        squad.description = fields["description"]
    if "instructions" in fields and fields["instructions"] is not None:
        squad.instructions = fields["instructions"]
    if "leader_agent_id" in fields and fields["leader_agent_id"] is not None:
        await _get_agent(db, fields["leader_agent_id"], squad.workspace_id)
        squad.leader_agent_id = fields["leader_agent_id"]
    await db.commit()
    return squad


async def delete_squad(db: AsyncSession, squad_id: str) -> None:
    squad = await get_squad(db, squad_id)
    await db.execute(delete(SquadMember).where(SquadMember.squad_id == squad_id))
    await db.delete(squad)
    await db.commit()


async def list_squad_members(db: AsyncSession, squad_id: str) -> list[SquadMember]:
    rows = await db.execute(select(SquadMember).where(SquadMember.squad_id == squad_id))
    return list(rows.scalars())


async def add_squad_member(
    db: AsyncSession, squad_id: str, member_type: str, member_id: str, role: str = ""
) -> None:
    if member_type not in ("agent", "member"):
        raise AutomationError(f"member_type inválido: {member_type}")
    squad = await get_squad(db, squad_id)
    if member_type == "agent":
        await _get_agent(db, member_id, squad.workspace_id)
    existing = await db.execute(
        select(SquadMember).where(
            SquadMember.squad_id == squad_id,
            SquadMember.member_type == member_type,
            SquadMember.member_id == member_id,
        )
    )
    row = existing.scalars().first()
    if row is None:
        db.add(SquadMember(squad_id=squad_id, member_type=member_type, member_id=member_id, role=role or ""))
        await db.commit()
    elif role and (row.role or "") != role:
        row.role = role
        await db.commit()


async def set_squad_member_role(
    db: AsyncSession, squad_id: str, member_type: str, member_id: str, role: str
) -> SquadMember:
    """PATCH /api/squads/{id}/members/role (multica UpdateSquadMemberRole)."""
    await get_squad(db, squad_id)
    existing = await db.execute(
        select(SquadMember).where(
            SquadMember.squad_id == squad_id,
            SquadMember.member_type == member_type,
            SquadMember.member_id == member_id,
        )
    )
    row = existing.scalars().first()
    if row is None:
        raise AutomationError("membro não encontrado nesta squad", 404)
    row.role = role or ""
    await db.commit()
    return row


async def list_squad_member_status(db: AsyncSession, squad_id: str) -> list[dict]:
    """GET /api/squads/{id}/members/status (multica ListSquadMemberStatus):
    status derivado de AgentTask ativa (working) / agente arquivado (archived)
    / idle, com as issues em que cada agente está trabalhando."""
    squad = await get_squad(db, squad_id)
    out: list[dict] = []
    for m in await list_squad_members(db, squad_id):
        entry: dict[str, Any] = {
            "member_type": m.member_type,
            "member_id": m.member_id,
            "role": getattr(m, "role", "") or "",
            "is_leader": m.member_type == "agent" and m.member_id == squad.leader_agent_id,
        }
        if m.member_type != "agent":
            entry.update({"status": "human", "issues": []})
            out.append(entry)
            continue
        agent = await db.get(Agent, m.member_id)
        if agent is None:
            entry.update({"status": "missing", "issues": []})
            out.append(entry)
            continue
        entry["name"] = agent.name
        entry["handle"] = agent.handle
        if getattr(agent, "archived_at", None) is not None:
            entry.update({"status": "archived", "issues": []})
            out.append(entry)
            continue
        rows = await db.execute(
            select(AgentTask).where(
                AgentTask.agent_id == agent.id,
                AgentTask.status.in_(["dispatched", "running"]),
            )
        )
        active_tasks = list(rows.scalars())
        issue_ids = {t.issue_id for t in active_tasks if t.issue_id}
        issues: list[dict] = []
        for iid in issue_ids:
            issue = await db.get(Issue, iid)
            if issue is not None:
                issues.append({"id": issue.id, "key": issue.key, "title": issue.title, "status": issue.status})
        entry.update({
            "status": "working" if active_tasks else "idle",
            "active_task_count": len(active_tasks),
            "issues": issues,
        })
        out.append(entry)
    return out


async def remove_squad_member(db: AsyncSession, squad_id: str, member_type: str, member_id: str) -> None:
    await db.execute(
        delete(SquadMember).where(
            SquadMember.squad_id == squad_id,
            SquadMember.member_type == member_type,
            SquadMember.member_id == member_id,
        )
    )
    await db.commit()


def _squad_handle(name: str) -> str:
    """Handle de menção da squad (@nome-da-squad)."""
    return (name or "").strip().lstrip("@").lower().replace(" ", "-")


async def build_squad_roster(db: AsyncSession, squad: Squad) -> str:
    """Roster dos membros com papéis, skills e mentions (multica buildSquadRoster)."""
    from ryu.models import AgentSkill, Skill

    lines: list[str] = []
    for m in await list_squad_members(db, squad.id):
        role = getattr(m, "role", "") or ""
        if m.member_type == "agent":
            ag = await db.get(Agent, m.member_id)
            if ag is None or getattr(ag, "archived_at", None) is not None:
                continue
            tag = "líder" if ag.id == squad.leader_agent_id else (role or "worker")
            rows = await db.execute(
                select(Skill.name).join(AgentSkill, AgentSkill.skill_id == Skill.id).where(AgentSkill.agent_id == ag.id)
            )
            skills = [name for (name,) in rows.all()]
            line = f"- agent '{ag.name}' (@{ag.handle}) — agent_id={ag.id} — papel: {tag}"
            if ag.description:
                line += f" — {ag.description[:160]}"
            if skills:
                line += f" — skills: {', '.join(skills[:8])}"
            lines.append(line)
        else:
            lines.append(f"- humano — member_id={m.member_id}" + (f" — papel: {role}" if role else ""))
    return "\n".join(lines) or "- (sem outros membros)"


async def build_squad_leader_briefing(
    db: AsyncSession, squad: Squad, issue: Issue, *, context: str = ""
) -> str:
    """Briefing operacional persistente do líder (multica buildSquadLeaderBriefing):
    protocolo + roster (papéis/skills) + instructions da squad, injetado em TODA
    task do líder relativa à squad — não apenas na primeira."""
    roster = await build_squad_roster(db, squad)
    parts = [
        f"Você é o líder da squad '{squad.name}'. A issue {issue.key} está atribuída à sua squad.",
    ]
    if getattr(squad, "description", ""):
        parts.append(f"## Sobre a squad\n{squad.description}")
    parts.append(
        "## Issue\n"
        f"Título: {issue.title}\n"
        f"Status: {issue.status}\n"
        f"Descrição:\n{issue.description or '(sem descrição)'}"
    )
    parts.append(f"## Membros da squad\n{roster}")
    if getattr(squad, "instructions", ""):
        parts.append(f"## Instruções da squad\n{squad.instructions}")
    parts.append(
        "## Protocolo operacional\n"
        "1. Avalie a situação atual da issue (novos comentários, sub-issues concluídas).\n"
        "2. Delegue: use a API do Ryu com seu token rat_ (Authorization: Bearer <token>) para "
        f"criar sub-issues (POST /api/issues, com parent_issue_id={issue.id}) e atribuí-las aos "
        "agentes da squad (assignee_type='agent') — a atribuição enfileira o trabalho automaticamente.\n"
        f"3. Acompanhe e comente o progresso na issue {issue.key} (POST /api/issues/{issue.id}/comments).\n"
        f"4. Ao final, mova a issue para in_review ou done (PATCH /api/issues/{issue.id}).\n"
        "5. SEMPRE registre sua decisão desta rodada: "
        f"POST /api/issues/{issue.id}/squad-evaluated com "
        f'{{"outcome": "action"|"no_action"|"failed", "squad_id": "{squad.id}"}}. '
        "Use 'no_action' quando nada precisa ser feito nesta rodada (nesse caso NÃO comente na issue)."
    )
    if context:
        parts.append(f"## Contexto desta rodada\n{context}")
    return "\n\n".join(parts)


async def enqueue_squad_leader_task(
    db: AsyncSession,
    squad: Squad,
    issue: Issue,
    actor_type: str,
    actor_id: str,
    *,
    context: str = "",
) -> AgentTask | None:
    """Enfileira task do líder com o briefing completo, com dedup de pendentes
    (multica enqueueSquadLeaderTask). NÃO commita; devolve a task nova/existente
    ou None quando o líder está indisponível."""
    leader = await db.get(Agent, squad.leader_agent_id)
    if leader is None or getattr(leader, "archived_at", None) is not None:
        return None
    # dedup: task PENDENTE (ainda não iniciada) do líder p/ a issue cobre a
    # rodada; uma task running não dedupa — o novo contexto vira nova rodada
    existing = await db.execute(
        select(AgentTask).where(
            AgentTask.issue_id == issue.id,
            AgentTask.agent_id == leader.id,
            AgentTask.status.in_(["queued", "dispatched"]),
        )
    )
    task = existing.scalars().first()
    if task is not None:
        return task
    task = AgentTask(
        workspace_id=squad.workspace_id,
        agent_id=leader.id,
        issue_id=issue.id,
        kind="issue",
        status="queued",
        prompt=await build_squad_leader_briefing(db, squad, issue, context=context),
    )
    db.add(task)
    await db.flush()
    await _log(
        db,
        squad.workspace_id,
        actor_type,
        actor_id,
        "squad_leader_task_queued",
        {"squad_id": squad.id, "task_id": task.id, "leader_agent_id": leader.id, "issue_key": issue.key},
        issue_id=issue.id,
    )
    return task


async def assign_issue_to_squad(
    db: AsyncSession, squad_id: str, issue_id: str, actor_type: str, actor_id: str
) -> AgentTask:
    """Atribui issue à squad (assignee_type='squad' de primeira classe) e
    enfileira a task de briefing (queued) para o leader_agent_id."""
    squad = await get_squad(db, squad_id)
    issue = await db.get(Issue, issue_id)
    if issue is None or issue.workspace_id != squad.workspace_id:
        raise AutomationError("issue não encontrada neste workspace", 404)
    leader = await _get_agent(db, squad.leader_agent_id, squad.workspace_id)
    if getattr(leader, "archived_at", None) is not None:
        raise AutomationError("líder da squad está arquivado", 409)
    if actor_type == "member":
        from ryu.services import agents as agents_svc

        if not await agents_svc.can_invoke_agent(db, actor_id, leader):
            raise AutomationError("sem permissão para invocar o líder desta squad", 403)

    # a issue permanece atribuída à SQUAD (não ao líder) — multica 084
    issue.assignee_type = "squad"
    issue.assignee_id = squad.id
    if issue.status in ("backlog",):
        issue.status = "todo"

    task = await enqueue_squad_leader_task(db, squad, issue, actor_type, actor_id)
    if task is None:
        raise AutomationError("líder da squad indisponível", 409)
    await _log(
        db,
        squad.workspace_id,
        actor_type,
        actor_id,
        "squad_assigned",
        {"squad_id": squad.id, "task_id": task.id, "leader_agent_id": leader.id, "issue_key": issue.key},
        issue_id=issue.id,
    )
    await db.commit()
    await hub.publish(squad.workspace_id, "issue:updated", issues_svc.issue_to_dict(issue))
    await hub.publish(
        squad.workspace_id,
        "task:queued",
        {"task_id": task.id, "agent_id": leader.id, "issue_id": issue.id, "kind": "issue"},
    )
    return task


# ── Squad leader evaluation (multica RecordSquadLeaderEvaluation) ─────
EVALUATION_OUTCOMES = ("action", "no_action", "failed")


async def record_squad_evaluation(
    db: AsyncSession,
    issue_id: str,
    actor_type: str,
    actor_id: str,
    *,
    outcome: str,
    squad_id: str | None = None,
) -> dict:
    """Registra a decisão do líder no activity_log (action|no_action|failed).

    O registro no_action é usado para suprimir efeitos colaterais — ex.: o
    comentário do líder para aquela rodada não é aceito (comment.go:1351)."""
    if outcome not in EVALUATION_OUTCOMES:
        raise AutomationError(f"outcome inválido: {outcome} (aceitos: {', '.join(EVALUATION_OUTCOMES)})")
    issue = await db.get(Issue, issue_id)
    if issue is None:
        raise AutomationError("issue não encontrada", 404)
    if squad_id:
        squad = await db.get(Squad, squad_id)
        if squad is None or squad.workspace_id != issue.workspace_id:
            raise AutomationError("squad não encontrada neste workspace", 404)
    entry = ActivityLog(
        workspace_id=issue.workspace_id,
        issue_id=issue.id,
        actor_type=actor_type,
        actor_id=actor_id,
        action="squad_evaluated",
        payload={"outcome": outcome, "squad_id": squad_id},
    )
    db.add(entry)
    await db.commit()
    await hub.publish(
        issue.workspace_id,
        "squad:evaluated",
        {"issue_id": issue.id, "squad_id": squad_id, "outcome": outcome, "agent_id": actor_id},
    )
    return {"issue_id": issue.id, "outcome": outcome, "squad_id": squad_id, "id": entry.id}


async def should_suppress_leader_comment(
    db: AsyncSession, issue: Issue, author_type: str, author_id: str
) -> bool:
    """no_action registrado nesta rodada bloqueia o comentário do líder
    (multica comment.go:1351). Rodada = a task mais recente do líder p/ a issue."""
    if author_type != "agent":
        return False
    # o autor lidera alguma squad deste workspace?
    rows = await db.execute(
        select(Squad).where(Squad.workspace_id == issue.workspace_id, Squad.leader_agent_id == author_id)
    )
    if rows.scalars().first() is None:
        return False
    last_task = (
        await db.execute(
            select(AgentTask)
            .where(AgentTask.issue_id == issue.id, AgentTask.agent_id == author_id)
            .order_by(AgentTask.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if last_task is None:
        return False
    rows = await db.execute(
        select(ActivityLog)
        .where(
            ActivityLog.issue_id == issue.id,
            ActivityLog.action == "squad_evaluated",
            ActivityLog.actor_type == "agent",
            ActivityLog.actor_id == author_id,
        )
        .order_by(ActivityLog.created_at.desc())
        .limit(1)
    )
    last_eval = rows.scalars().first()
    if last_eval is None:
        return False
    if (last_eval.payload or {}).get("outcome") != "no_action":
        return False
    # avaliação pertence à rodada atual (registrada depois do enfileiramento da task)
    eval_at, task_at = last_eval.created_at, last_task.created_at
    if eval_at is not None and eval_at.tzinfo is None:
        from datetime import timezone as _tz

        eval_at = eval_at.replace(tzinfo=_tz.utc)
    if task_at is not None and task_at.tzinfo is None:
        from datetime import timezone as _tz

        task_at = task_at.replace(tzinfo=_tz.utc)
    return eval_at is not None and task_at is not None and eval_at >= task_at


def _should_suppress_squad_leader_self_trigger(squad: Squad, author_type: str, author_id: str) -> bool:
    """Comentário do próprio líder não re-aciona o líder (squad.go:991)."""
    return author_type == "agent" and author_id == squad.leader_agent_id


async def _is_squad_worker(db: AsyncSession, squad: Squad, agent_id: str) -> bool:
    rows = await db.execute(
        select(SquadMember).where(
            SquadMember.squad_id == squad.id,
            SquadMember.member_type == "agent",
            SquadMember.member_id == agent_id,
        )
    )
    return rows.scalars().first() is not None


async def handle_comment_squad_triggers(
    db: AsyncSession, issue: Issue, author_type: str, author_id: str, body: str
) -> list[AgentTask]:
    """Loop de delegação (multica computeCommentAgentTriggers):

    - comentário em issue atribuída a squad re-aciona o líder (com dedup);
    - self-trigger do líder é suprimido; worker da MESMA squad acorda o líder;
    - menção @squad no corpo aciona o líder da squad mencionada.

    Best-effort: nunca derruba a criação do comentário. Commita as tasks."""
    squads: dict[str, Squad] = {}
    # (a) issue atribuída a squad
    if issue.assignee_type == "squad" and issue.assignee_id:
        squad = await db.get(Squad, issue.assignee_id)
        if squad is not None:
            squads[squad.id] = squad
    # (b) menção @squad
    if body and "@" in body:
        handles = {h.lower() for h in issues_svc.MENTION_RE.findall(body)}
        if handles:
            rows = await db.execute(select(Squad).where(Squad.workspace_id == issue.workspace_id))
            for squad in rows.scalars():
                if _squad_handle(squad.name) in handles:
                    squads[squad.id] = squad

    tasks: list[AgentTask] = []
    for squad in squads.values():
        if _should_suppress_squad_leader_self_trigger(squad, author_type, author_id):
            continue  # líder não se auto-aciona
        # workers da mesma squad PODEM acordar o líder (exceção explícita);
        # humanos e agentes de fora também acionam — só o próprio líder não.
        author_label = author_id
        if author_type == "agent":
            ag = await db.get(Agent, author_id)
            author_label = f"agente @{ag.handle}" if ag else f"agente {author_id}"
            if ag is not None and await _is_squad_worker(db, squad, ag.id):
                author_label += " (worker da squad)"
        context = f"Novo comentário de {author_label} na issue {issue.key}:\n\n{body.strip()[:4000]}"
        task = await enqueue_squad_leader_task(db, squad, issue, author_type, author_id, context=context)
        if task is not None:
            tasks.append(task)
    if tasks:
        await db.commit()
        for t in tasks:
            await hub.publish(
                issue.workspace_id,
                "task:queued",
                {"task_id": t.id, "agent_id": t.agent_id, "issue_id": issue.id, "kind": "issue"},
            )
    return tasks


async def squad_briefing_on_assign(
    db: AsyncSession, issue: Issue, actor_type: str, actor_id: str
) -> AgentTask | None:
    """Hook do tracker: issue com assignee_type='squad' em todo/in_progress →
    enfileira briefing do líder (dedup). NÃO commita (segue o padrão de
    _maybe_enqueue_agent_task do serviço de issues)."""
    if issue.assignee_type != "squad" or not issue.assignee_id:
        return None
    if issue.status not in ("todo", "in_progress"):
        return None
    squad = await db.get(Squad, issue.assignee_id)
    if squad is None or squad.workspace_id != issue.workspace_id:
        return None
    return await enqueue_squad_leader_task(db, squad, issue, actor_type, actor_id)
