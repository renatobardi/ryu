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

import secrets
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import SessionLocal
from ryu.models import (
    ActivityLog,
    Agent,
    AgentSkill,
    AgentTask,
    Autopilot,
    AutopilotRun,
    Issue,
    Skill,
    Squad,
    SquadMember,
    now,
)
from ryu.realtime.hub import hub
from ryu.services import issues as issues_svc

TRIGGER_TYPES = ["cron", "webhook", "manual"]


class AutomationError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ── serializers ───────────────────────────────────────────────────────
def skill_to_dict(s: Skill) -> dict:
    return {
        "id": s.id,
        "workspace_id": s.workspace_id,
        "name": s.name,
        "description": s.description,
        "content": s.content,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def autopilot_to_dict(a: Autopilot) -> dict:
    return {
        "id": a.id,
        "workspace_id": a.workspace_id,
        "name": a.name,
        "enabled": a.enabled,
        "trigger_type": a.trigger_type,
        "cron_expr": a.cron_expr,
        "webhook_token": a.webhook_token,
        "rule": a.rule,
        "target_agent_id": a.target_agent_id,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


def run_to_dict(r: AutopilotRun) -> dict:
    return {
        "id": r.id,
        "autopilot_id": r.autopilot_id,
        "status": r.status,
        "issue_id": r.issue_id,
        "detail": r.detail,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def squad_to_dict(s: Squad, members: list[SquadMember] | None = None) -> dict:
    d = {
        "id": s.id,
        "workspace_id": s.workspace_id,
        "name": s.name,
        "leader_agent_id": s.leader_agent_id,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }
    if members is not None:
        d["members"] = [
            {"member_type": m.member_type, "member_id": m.member_id} for m in members
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
async def create_skill(
    db: AsyncSession, workspace_id: str, name: str, description: str = "", content: str = ""
) -> Skill:
    if not name.strip():
        raise AutomationError("name é obrigatório")
    skill = Skill(
        workspace_id=workspace_id, name=name.strip(), description=description or "", content=content or ""
    )
    db.add(skill)
    await db.commit()
    return skill


async def list_skills(db: AsyncSession, workspace_id: str) -> list[Skill]:
    rows = await db.execute(
        select(Skill).where(Skill.workspace_id == workspace_id).order_by(Skill.created_at)
    )
    return list(rows.scalars())


async def get_skill(db: AsyncSession, skill_id: str) -> Skill:
    skill = await db.get(Skill, skill_id)
    if skill is None:
        raise AutomationError("skill não encontrada", 404)
    return skill


async def update_skill(db: AsyncSession, skill_id: str, fields: dict[str, Any]) -> Skill:
    skill = await get_skill(db, skill_id)
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


# ═══════════════════════════ AUTOPILOTS ═══════════════════════════════
# referência ao scheduler (setada em register_autopilot_jobs no lifespan)
_scheduler = None


def _job_id(autopilot_id: str) -> str:
    return f"autopilot:{autopilot_id}"


def _schedule(ap: Autopilot) -> None:
    """(Re)agenda o job cron de um autopilot no scheduler global, se houver."""
    if _scheduler is None:
        return
    from apscheduler.triggers.cron import CronTrigger

    try:
        _scheduler.remove_job(_job_id(ap.id))
    except Exception:
        pass
    if ap.enabled and ap.trigger_type == "cron" and ap.cron_expr:
        _scheduler.add_job(
            _cron_fire,
            CronTrigger.from_crontab(ap.cron_expr),
            args=[ap.id],
            id=_job_id(ap.id),
            replace_existing=True,
        )


def _unschedule(autopilot_id: str) -> None:
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(_job_id(autopilot_id))
    except Exception:
        pass


async def _cron_fire(autopilot_id: str) -> None:
    """Executado pelo APScheduler — abre sessão própria."""
    async with SessionLocal() as db:
        ap = await db.get(Autopilot, autopilot_id)
        if ap is None or not ap.enabled:
            return
        try:
            await run_autopilot(db, ap, source="cron")
        except Exception:
            pass  # falha já registrada no AutopilotRun quando possível


async def register_autopilot_jobs(scheduler) -> None:
    """Chamado pelo main no lifespan: cria um job por autopilot habilitado com cron_expr."""
    global _scheduler
    _scheduler = scheduler
    async with SessionLocal() as db:
        rows = await db.execute(
            select(Autopilot).where(
                Autopilot.enabled == True,  # noqa: E712
                Autopilot.trigger_type == "cron",
                Autopilot.cron_expr.is_not(None),
            )
        )
        for ap in rows.scalars():
            _schedule(ap)


def _validate_cron(expr: str) -> None:
    from apscheduler.triggers.cron import CronTrigger

    try:
        CronTrigger.from_crontab(expr)
    except ValueError as e:
        raise AutomationError(f"cron_expr inválida: {e}")


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
) -> Autopilot:
    if not name.strip():
        raise AutomationError("name é obrigatório")
    if trigger_type not in TRIGGER_TYPES:
        raise AutomationError(f"trigger_type inválido: {trigger_type}")
    if trigger_type == "cron":
        if not cron_expr:
            raise AutomationError("cron_expr é obrigatório para trigger cron")
        _validate_cron(cron_expr)
    if target_agent_id:
        await _get_agent(db, target_agent_id, workspace_id)
    ap = Autopilot(
        workspace_id=workspace_id,
        name=name.strip(),
        enabled=enabled,
        trigger_type=trigger_type,
        cron_expr=cron_expr,
        webhook_token=f"awh_{secrets.token_urlsafe(24)}" if trigger_type == "webhook" else None,
        rule=rule or "",
        target_agent_id=target_agent_id,
    )
    db.add(ap)
    await db.commit()
    _schedule(ap)
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


async def update_autopilot(db: AsyncSession, autopilot_id: str, fields: dict[str, Any]) -> Autopilot:
    ap = await get_autopilot(db, autopilot_id)
    if "trigger_type" in fields and fields["trigger_type"] is not None:
        if fields["trigger_type"] not in TRIGGER_TYPES:
            raise AutomationError(f"trigger_type inválido: {fields['trigger_type']}")
        ap.trigger_type = fields["trigger_type"]
        if ap.trigger_type == "webhook" and not ap.webhook_token:
            ap.webhook_token = f"awh_{secrets.token_urlsafe(24)}"
    for k in ("name", "rule", "cron_expr", "target_agent_id", "enabled"):
        if k in fields and fields[k] is not None:
            setattr(ap, k, fields[k])
    if ap.trigger_type == "cron":
        if not ap.cron_expr:
            raise AutomationError("cron_expr é obrigatório para trigger cron")
        _validate_cron(ap.cron_expr)
    if ap.target_agent_id:
        await _get_agent(db, ap.target_agent_id, ap.workspace_id)
    await db.commit()
    _schedule(ap)
    return ap


async def delete_autopilot(db: AsyncSession, autopilot_id: str) -> None:
    ap = await get_autopilot(db, autopilot_id)
    await db.execute(delete(AutopilotRun).where(AutopilotRun.autopilot_id == autopilot_id))
    await db.delete(ap)
    await db.commit()
    _unschedule(autopilot_id)


async def list_runs(db: AsyncSession, autopilot_id: str, limit: int = 50) -> list[AutopilotRun]:
    rows = await db.execute(
        select(AutopilotRun)
        .where(AutopilotRun.autopilot_id == autopilot_id)
        .order_by(AutopilotRun.created_at.desc())
        .limit(limit)
    )
    return list(rows.scalars())


async def run_autopilot(db: AsyncSession, ap: Autopilot, source: str = "manual") -> AutopilotRun:
    """Executa um autopilot: cria AutopilotRun + Issue a partir de `rule`.

    A issue nasce atribuída ao target_agent_id com status todo — o que
    enfileira AgentTask (status queued) pela mesma lógica do tracker.
    """
    run = AutopilotRun(autopilot_id=ap.id, status="running", detail=f"trigger: {source}")
    db.add(run)
    await db.commit()

    try:
        title = f"[Autopilot] {ap.name} — {now().strftime('%Y-%m-%d %H:%M')}"
        has_agent = bool(ap.target_agent_id)
        issue = await issues_svc.create_issue(
            db,
            ap.workspace_id,
            "system",
            f"autopilot:{ap.id}",
            title=title,
            description=ap.rule or "",
            status="todo" if has_agent else "backlog",
            assignee_type="agent" if has_agent else None,
            assignee_id=ap.target_agent_id if has_agent else None,
        )
        run.status = "done"
        run.issue_id = issue.id
        run.detail = f"trigger: {source}; issue {issue.key}"
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
    except Exception as e:  # registra falha na run
        run.status = "failed"
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
            "source": source,
        },
    )
    return run


# ═══════════════════════════ SQUADS ═══════════════════════════════════
async def create_squad(db: AsyncSession, workspace_id: str, name: str, leader_agent_id: str) -> Squad:
    if not name.strip():
        raise AutomationError("name é obrigatório")
    await _get_agent(db, leader_agent_id, workspace_id)
    squad = Squad(workspace_id=workspace_id, name=name.strip(), leader_agent_id=leader_agent_id)
    db.add(squad)
    await db.flush()
    # líder entra como membro automaticamente
    db.add(SquadMember(squad_id=squad.id, member_type="agent", member_id=leader_agent_id))
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


async def add_squad_member(db: AsyncSession, squad_id: str, member_type: str, member_id: str) -> None:
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
    if existing.first() is None:
        db.add(SquadMember(squad_id=squad_id, member_type=member_type, member_id=member_id))
        await db.commit()


async def remove_squad_member(db: AsyncSession, squad_id: str, member_type: str, member_id: str) -> None:
    await db.execute(
        delete(SquadMember).where(
            SquadMember.squad_id == squad_id,
            SquadMember.member_type == member_type,
            SquadMember.member_id == member_id,
        )
    )
    await db.commit()


def _briefing_prompt(squad: Squad, issue: Issue, member_lines: list[str]) -> str:
    members = "\n".join(f"- {ln}" for ln in member_lines) or "- (sem outros membros)"
    return (
        f"Você é o líder da squad '{squad.name}'. A issue {issue.key} foi atribuída à sua squad.\n\n"
        f"## Issue\n"
        f"Título: {issue.title}\n"
        f"Descrição:\n{issue.description or '(sem descrição)'}\n\n"
        f"## Membros da squad\n{members}\n\n"
        f"## Sua missão\n"
        f"1. Analise a issue e quebre o trabalho em sub-issues quando fizer sentido.\n"
        f"2. Delegue: use a API do Ryu com seu token rat_ (Authorization: Bearer <token>) para "
        f"criar sub-issues (POST /api/issues, com parent_issue_id={issue.id}) e atribuí-las aos "
        f"agentes da squad (assignee_type='agent') — a atribuição enfileira o trabalho automaticamente.\n"
        f"3. Acompanhe e comente o progresso na issue {issue.key} (POST /api/issues/{issue.id}/comments).\n"
        f"4. Ao final, mova a issue para in_review ou done (PATCH /api/issues/{issue.id})."
    )


async def assign_issue_to_squad(
    db: AsyncSession, squad_id: str, issue_id: str, actor_type: str, actor_id: str
) -> AgentTask:
    """Atribui issue à squad: task de briefing (queued) para o leader_agent_id."""
    squad = await get_squad(db, squad_id)
    issue = await db.get(Issue, issue_id)
    if issue is None or issue.workspace_id != squad.workspace_id:
        raise AutomationError("issue não encontrada neste workspace", 404)
    leader = await _get_agent(db, squad.leader_agent_id, squad.workspace_id)

    # monta linhas dos membros (nomes dos agents quando possível)
    member_lines: list[str] = []
    for m in await list_squad_members(db, squad_id):
        if m.member_type == "agent" and m.member_id != leader.id:
            ag = await db.get(Agent, m.member_id)
            if ag:
                member_lines.append(f"agent '{ag.name}' ({ag.handle}) — agent_id={ag.id}")
        elif m.member_type == "member":
            member_lines.append(f"member humano — member_id={m.member_id}")

    # issue passa a apontar para o líder; status vai para in_progress-ready (todo)
    issue.assignee_type = "agent"
    issue.assignee_id = leader.id
    if issue.status in ("backlog",):
        issue.status = "todo"

    # dedupe: não duplica task ativa do líder para esta issue
    existing = await db.execute(
        select(AgentTask).where(
            AgentTask.issue_id == issue.id,
            AgentTask.agent_id == leader.id,
            AgentTask.status.in_(["queued", "dispatched", "running"]),
        )
    )
    task = existing.scalars().first()
    if task is None:
        task = AgentTask(
            workspace_id=squad.workspace_id,
            agent_id=leader.id,
            issue_id=issue.id,
            kind="issue",
            status="queued",
            prompt=_briefing_prompt(squad, issue, member_lines),
        )
        db.add(task)
        await db.flush()
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
