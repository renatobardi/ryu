"""Serviço do domínio AUTOPILOTS.

- Autopilots: CRUD + execução (cron via APScheduler, webhook, manual).
  Cada run cria AutopilotRun + Issue a partir de `rule`, atribuída ao
  target_agent_id — o que enfileira AgentTask (status queued) pela mesma
  lógica do tracker (reuso de ryu.services.issues.create_issue).
- Triggers, permissões/colaboradores, subscribers, rule versions e o
  agendamento dos jobs cron no scheduler global.
- Helpers compartilhados (AutomationError, _iso, _log, _get_agent) usados
  pelos serviços de skills, squads e webhooks.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import SessionLocal
from ryu.models import (
    ActivityLog,
    Agent,
    AgentTask,
    Autopilot,
    AutopilotCollaborator,
    AutopilotRuleVersion,
    AutopilotRun,
    AutopilotSubscriber,
    AutopilotTrigger,
    Issue,
    Member,
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


class AutomationError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ── serializers ───────────────────────────────────────────────────────
def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


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
