"""Serviço do domínio SQUADS.

- CRUD de squads + membros (SquadMember) e status derivado dos membros.
- Atribuir issue a squad cria AgentTask queued para o leader_agent_id com
  prompt de briefing pedindo delegação.
- Loop de delegação por comentário/menção @squad e registro da avaliação do líder.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.models import (
    ActivityLog,
    Agent,
    AgentTask,
    Issue,
    Squad,
    SquadMember,
)
from ryu.realtime.hub import hub
from ryu.services import issues as issues_svc
from ryu.services.automation import AutomationError, _get_agent, _log


# ── serializers ───────────────────────────────────────────────────────
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
