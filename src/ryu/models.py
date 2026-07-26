"""Modelo de dados do Ryu — núcleo copiado do design do multica.

Decisões herdadas: assignee polimórfico (assignee_type+assignee_id),
position FLOAT no board, fila de tasks em tabela, três tipos de token.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def uid() -> str:
    return uuid.uuid4().hex


def now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


# ── Identidade / tenancy ──────────────────────────────────────────────
class User(Base, TimestampMixin):
    __tablename__ = "user"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, default="")


class Workspace(Base, TimestampMixin):
    __tablename__ = "workspace"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String)
    issue_prefix: Mapped[str] = mapped_column(String, default="RYU")
    issue_counter: Mapped[int] = mapped_column(Integer, default=0)


class Member(Base, TimestampMixin):
    __tablename__ = "member"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user.id"), index=True)
    role: Mapped[str] = mapped_column(String, default="member")  # owner|admin|member


class VerificationCode(Base):
    __tablename__ = "verification_code"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String, index=True)
    code: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class ApiToken(Base, TimestampMixin):
    """Três prefixos: ryu_ (PAT usuário), rdt_ (daemon), rat_ (task de agente)."""
    __tablename__ = "api_token"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    kind: Mapped[str] = mapped_column(String)  # pat|daemon|task
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


# ── Projects ──────────────────────────────────────────────────────────
class Project(Base, TimestampMixin):
    __tablename__ = "project"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="active")  # active|archived


# ── Tracker ───────────────────────────────────────────────────────────
class Issue(Base, TimestampMixin):
    __tablename__ = "issue"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), index=True)
    key: Mapped[str] = mapped_column(String, index=True)  # RYU-123
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="backlog", index=True)
    # backlog|todo|in_progress|in_review|done|blocked|cancelled
    priority: Mapped[str] = mapped_column(String, default="none")  # urgent|high|medium|low|none
    assignee_type: Mapped[str | None] = mapped_column(String, nullable=True)  # member|agent
    assignee_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    creator_type: Mapped[str] = mapped_column(String, default="member")
    creator_id: Mapped[str] = mapped_column(String)
    parent_issue_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    position: Mapped[float] = mapped_column(Float, default=0.0)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # KV usado por agentes


class Label(Base, TimestampMixin):
    __tablename__ = "label"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    color: Mapped[str] = mapped_column(String, default="#8b5cf6")


class IssueLabel(Base):
    __tablename__ = "issue_label"
    issue_id: Mapped[str] = mapped_column(ForeignKey("issue.id"), primary_key=True)
    label_id: Mapped[str] = mapped_column(ForeignKey("label.id"), primary_key=True)


class Comment(Base, TimestampMixin):
    __tablename__ = "comment"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    issue_id: Mapped[str] = mapped_column(ForeignKey("issue.id"), index=True)
    author_type: Mapped[str] = mapped_column(String)  # member|agent|system
    author_id: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    parent_comment_id: Mapped[str | None] = mapped_column(String, nullable=True)


class ActivityLog(Base):
    __tablename__ = "activity_log"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    issue_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    actor_type: Mapped[str] = mapped_column(String)
    actor_id: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)  # created|status_changed|assigned|commented|...
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ── Agentes / execução ────────────────────────────────────────────────
class Agent(Base, TimestampMixin):
    __tablename__ = "agent"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    handle: Mapped[str] = mapped_column(String, index=True)  # @codebot
    description: Mapped[str] = mapped_column(Text, default="")
    runtime: Mapped[str] = mapped_column(String, default="claude")  # claude|codex|gemini|...
    runtime_config: Mapped[dict] = mapped_column(JSON, default=dict)  # cmd extra, cwd, env, repo_url
    status: Mapped[str] = mapped_column(String, default="idle")  # idle|working|blocked|error|offline
    max_concurrent_tasks: Mapped[int] = mapped_column(Integer, default=1)


class AgentTask(Base, TimestampMixin):
    """A fila é esta tabela. queued→dispatched→running→completed|failed|cancelled."""
    __tablename__ = "agent_task"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agent.id"), index=True)
    issue_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    chat_session_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    kind: Mapped[str] = mapped_column(String, default="issue")  # issue|chat
    status: Mapped[str] = mapped_column(String, default="queued", index=True)
    prompt: Mapped[str] = mapped_column(Text, default="")
    result_summary: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)


class TaskMessage(Base):
    __tablename__ = "task_message"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey("agent_task.id"), index=True)
    role: Mapped[str] = mapped_column(String)  # progress|stdout|stderr|system
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ── Skills ────────────────────────────────────────────────────────────
class Skill(Base, TimestampMixin):
    __tablename__ = "skill"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")  # markdown


class AgentSkill(Base):
    __tablename__ = "agent_skill"
    agent_id: Mapped[str] = mapped_column(ForeignKey("agent.id"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skill.id"), primary_key=True)


# ── Squads ────────────────────────────────────────────────────────────
class Squad(Base, TimestampMixin):
    __tablename__ = "squad"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    leader_agent_id: Mapped[str] = mapped_column(String)


class SquadMember(Base):
    __tablename__ = "squad_member"
    squad_id: Mapped[str] = mapped_column(ForeignKey("squad.id"), primary_key=True)
    member_type: Mapped[str] = mapped_column(String, primary_key=True)  # agent|member
    member_id: Mapped[str] = mapped_column(String, primary_key=True)


# ── Autopilots ────────────────────────────────────────────────────────
class Autopilot(Base, TimestampMixin):
    __tablename__ = "autopilot"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    trigger_type: Mapped[str] = mapped_column(String, default="cron")  # cron|webhook|manual
    cron_expr: Mapped[str | None] = mapped_column(String, nullable=True)
    webhook_token: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    rule: Mapped[str] = mapped_column(Text, default="")  # instrução → vira issue
    target_agent_id: Mapped[str | None] = mapped_column(String, nullable=True)


class AutopilotRun(Base):
    __tablename__ = "autopilot_run"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    autopilot_id: Mapped[str] = mapped_column(ForeignKey("autopilot.id"), index=True)
    status: Mapped[str] = mapped_column(String, default="running")  # running|done|failed
    issue_id: Mapped[str | None] = mapped_column(String, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ── Chat ──────────────────────────────────────────────────────────────
class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_session"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String, default="Nova conversa")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)


class ChatMessage(Base):
    __tablename__ = "chat_message"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_session.id"), index=True)
    role: Mapped[str] = mapped_column(String)  # user|agent|system
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ── Inbox ─────────────────────────────────────────────────────────────
class InboxItem(Base):
    __tablename__ = "inbox_item"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    severity: Mapped[str] = mapped_column(String, default="info")  # action_required|attention|info
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text, default="")
    issue_id: Mapped[str | None] = mapped_column(String, nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
