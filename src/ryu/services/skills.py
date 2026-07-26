"""Serviço do domínio SKILLS.

- CRUD de skills (markdown) + attach/detach em agents (AgentSkill).
- Arquivos de apoio da skill (SkillFile) e labels (SkillLabel).
- Import de skill a partir de .md/.zip e do filesystem do runtime local.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.models import (
    Agent,
    AgentSkill,
    Label,
    Skill,
    SkillFile,
    SkillLabel,
)
from ryu.services.automation import AutomationError, _get_agent, _iso

IMPORT_CONFLICT_STRATEGIES = ("fail", "overwrite", "rename", "skip")


# ── serializers ───────────────────────────────────────────────────────
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
