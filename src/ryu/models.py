"""Modelo de dados do Ryu — núcleo copiado do design do multica.

Decisões herdadas: assignee polimórfico (assignee_type+assignee_id),
position FLOAT no board, fila de tasks em tabela, três tipos de token.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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
    # workspace-auth ciclo 1 — campos editáveis via PATCH /api/workspaces/{id}
    description: Mapped[str] = mapped_column(Text, default="")
    context: Mapped[str] = mapped_column(Text, default="")
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    repos: Mapped[list] = mapped_column(JSON, default=list)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)


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
    # hardening (multica 010_verification_code_attempts): cap de 5 tentativas
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


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
    # workspace-auth ciclo 1 (multica 011_personal_access_tokens)
    token_prefix: Mapped[str] = mapped_column(String, default="")  # 12 primeiros chars do raw
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Invitation(Base, TimestampMixin):
    """Convite de workspace (multica 001_init invitation)."""

    __tablename__ = "invitation"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), index=True)
    inviter_id: Mapped[str] = mapped_column(ForeignKey("user.id"))
    invitee_email: Mapped[str] = mapped_column(String, index=True)
    invitee_user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    role: Mapped[str] = mapped_column(String, default="member")  # admin|member (nunca owner)
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    # pending|accepted|declined|revoked|expired
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationPreference(Base, TimestampMixin):
    """Preferências de notificação por (workspace, user) — multica 064."""

    __tablename__ = "notification_preference"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)  # grupo -> all|muted


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
    # bag de valores de propriedades customizadas, keyed por UUID da definição
    properties: Mapped[dict] = mapped_column(JSON, default=dict)


class Label(Base, TimestampMixin):
    __tablename__ = "label"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    color: Mapped[str] = mapped_column(String, default="#8b5cf6")
    # namespaces independentes por tipo de recurso (multica 162_resource_labels)
    resource_type: Mapped[str] = mapped_column(String, default="issue")  # issue|agent|skill
    description: Mapped[str] = mapped_column(Text, default="")


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
    # resolve/unresolve de thread (só no comentário raiz)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_type: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved_by_id: Mapped[str | None] = mapped_column(String, nullable=True)


class Attachment(Base):
    """Upload vinculado a issue e/ou comentário (paridade multica 029_attachment)."""

    __tablename__ = "attachment"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), index=True)
    issue_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    comment_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    uploader_type: Mapped[str] = mapped_column(String)  # member|agent
    uploader_id: Mapped[str] = mapped_column(String)
    filename: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String, default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IssueSubscriber(Base):
    """Fan-out de notificações (paridade multica 015_issue_subscriber)."""

    __tablename__ = "issue_subscriber"
    issue_id: Mapped[str] = mapped_column(ForeignKey("issue.id"), primary_key=True)
    user_type: Mapped[str] = mapped_column(String, primary_key=True)  # member|agent
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    reason: Mapped[str] = mapped_column(String, default="manual")
    # creator|assignee|commenter|mentioned|manual
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IssueProperty(Base, TimestampMixin):
    """Catálogo de propriedades customizadas por workspace (multica 191/196)."""

    __tablename__ = "issue_property"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)  # text|number|select|multi_select|date|checkbox|url
    description: Mapped[str] = mapped_column(Text, default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # select: {"options": [...]}
    icon: Mapped[str] = mapped_column(String, default="")
    position: Mapped[float] = mapped_column(Float, default=0.0)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IssueReaction(Base):
    __tablename__ = "issue_reaction"
    __table_args__ = (UniqueConstraint("issue_id", "actor_type", "actor_id", "emoji"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    issue_id: Mapped[str] = mapped_column(ForeignKey("issue.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    actor_type: Mapped[str] = mapped_column(String)  # member|agent
    actor_id: Mapped[str] = mapped_column(String)
    emoji: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CommentReaction(Base):
    __tablename__ = "comment_reaction"
    __table_args__ = (UniqueConstraint("comment_id", "actor_type", "actor_id", "emoji"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    comment_id: Mapped[str] = mapped_column(ForeignKey("comment.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    actor_type: Mapped[str] = mapped_column(String)  # member|agent
    actor_id: Mapped[str] = mapped_column(String)
    emoji: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PinnedItem(Base):
    """Itens fixados por usuário na sidebar (multica 038_pinned_items)."""

    __tablename__ = "pinned_item"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", "item_type", "item_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    item_type: Mapped[str] = mapped_column(String)  # issue|project
    item_id: Mapped[str] = mapped_column(String)
    position: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


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


# ── Daemon / runtimes externos ────────────────────────────────────────
class AgentRuntime(Base, TimestampMixin):
    """Runtime de agente registrado por um daemon externo (multica 004).

    Um registro por (workspace, daemon_id, provider). O daemon detecta os
    CLIs locais e registra cada um; online/offline deriva de last_seen_at.
    """

    __tablename__ = "agent_runtime"
    __table_args__ = (UniqueConstraint("workspace_id", "daemon_id", "provider"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), index=True)
    daemon_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String, default="Local Agent")
    device_name: Mapped[str] = mapped_column(String, default="")
    runtime_mode: Mapped[str] = mapped_column(String, default="local")  # local (cloud fora de escopo)
    provider: Mapped[str] = mapped_column(String)  # ver ryu.providers
    version: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="offline")  # online|offline
    device_info: Mapped[str] = mapped_column(String, default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── Agentes / execução ────────────────────────────────────────────────
class Agent(Base, TimestampMixin):
    __tablename__ = "agent"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    handle: Mapped[str] = mapped_column(String, index=True)  # @codebot
    description: Mapped[str] = mapped_column(Text, default="")
    runtime: Mapped[str] = mapped_column(String, default="claude")  # provider; ver ryu.providers
    runtime_config: Mapped[dict] = mapped_column(JSON, default=dict)  # cmd extra, cwd, env, repo_url
    status: Mapped[str] = mapped_column(String, default="idle")  # idle|working|blocked|error|offline
    max_concurrent_tasks: Mapped[int] = mapped_column(Integer, default=1)
    # dono + permissão de invocação (multica 130_agent_invocation_permission)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True, index=True)  # user_id do dono
    visibility: Mapped[str] = mapped_column(String, default="workspace")  # workspace|private
    permission_mode: Mapped[str] = mapped_column(String, default="public_to")  # private|public_to
    # archive/soft-delete (multica 031_agent_archive)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[str | None] = mapped_column(String, nullable=True)
    # configuração de execução aplicada ao run (multica 021/050/095/212)
    instructions: Mapped[str] = mapped_column(Text, default="")  # system prompt persistente
    model: Mapped[str | None] = mapped_column(String, nullable=True)  # --model do runtime
    thinking_level: Mapped[str | None] = mapped_column(String, nullable=True)  # none|low|medium|high
    service_tier: Mapped[str | None] = mapped_column(String, nullable=True)  # standard|flex|priority


class AgentInvocationTarget(Base):
    """Allow-list de invocação quando agent.permission_mode = public_to."""
    __tablename__ = "agent_invocation_target"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agent.id"), index=True)
    target_type: Mapped[str] = mapped_column(String)  # workspace|member
    target_id: Mapped[str] = mapped_column(String)  # workspace_id ou user_id/member_id
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


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
    # retry automático (multica 055_task_lease_and_retry)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    retry_of_task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    rerun_of_task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    # crash|timeout|lease_expired|queued_ttl|agent_archived|agent_missing
    # continuidade de sessão do runtime + reuso de work_dir (multica 020_task_session)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    work_dir: Mapped[str | None] = mapped_column(String, nullable=True)
    # heartbeat/lease (multica 055) + cancelamento efetivo
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    # runtime externo que reivindicou a task (daemon claim; multica 004 runtime_id)
    runtime_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)


class TaskMessage(Base):
    __tablename__ = "task_message"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey("agent_task.id"), index=True)
    role: Mapped[str] = mapped_column(String)  # progress|stdout|stderr|system|assistant|tool_use|tool_result
    content: Mapped[str] = mapped_column(Text)
    # transcript estruturado (multica 026_task_messages)
    seq: Mapped[int] = mapped_column(Integer, default=0, index=True)
    type: Mapped[str] = mapped_column(String, default="")  # assistant|tool_use|tool_result|system|stdout
    tool: Mapped[str] = mapped_column(String, default="")
    input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TaskUsage(Base):
    """Usage por (task, provider, model) — multica 032_task_usage."""
    __tablename__ = "task_usage"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey("agent_task.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    provider: Mapped[str] = mapped_column(String, default="")
    model: Mapped[str] = mapped_column(String, default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    # usage-observability ciclo 1 (paridade multica pricing.go + runtime dim)
    runtime: Mapped[str] = mapped_column(String, default="")  # agent.runtime no momento do registro
    costed: Mapped[bool] = mapped_column(Boolean, default=True)  # False = custo estimado via pricing table
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ── Usage observability: rollups incrementais ─────────────────────────
class UsageRollupState(Base):
    """Watermark do job incremental de rollup — 1 linha (key='usage').

    Guarda o `created_at` mais recente de TaskUsage já processado, evitando
    reprocessar tudo a cada tick (paridade multica *_dirty/*_rollup_state)."""

    __tablename__ = "usage_rollup_state"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    last_processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rows_processed: Mapped[int] = mapped_column(Integer, default=0)


class UsageRollupHourly(Base):
    """Rollup incremental por hora — dimensão (workspace, agent, runtime, provider, model)."""

    __tablename__ = "usage_rollup_hourly"
    __table_args__ = (
        UniqueConstraint("workspace_id", "bucket", "agent_id", "runtime", "provider", "model"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    bucket: Mapped[str] = mapped_column(String, index=True)  # "YYYY-MM-DDTHH" (UTC)
    agent_id: Mapped[str] = mapped_column(String, default="", index=True)
    runtime: Mapped[str] = mapped_column(String, default="")
    provider: Mapped[str] = mapped_column(String, default="")
    model: Mapped[str] = mapped_column(String, default="")
    task_count: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd_costed: Mapped[float] = mapped_column(Float, default=0.0)
    cost_usd_estimated: Mapped[float] = mapped_column(Float, default=0.0)
    uncosted_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class UsageRollupDaily(Base):
    """Rollup incremental por dia — mesma dimensão do hourly + tempo de execução."""

    __tablename__ = "usage_rollup_daily"
    __table_args__ = (
        UniqueConstraint("workspace_id", "bucket", "agent_id", "runtime", "provider", "model"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    bucket: Mapped[str] = mapped_column(String, index=True)  # "YYYY-MM-DD" (UTC)
    agent_id: Mapped[str] = mapped_column(String, default="", index=True)
    runtime: Mapped[str] = mapped_column(String, default="")
    provider: Mapped[str] = mapped_column(String, default="")
    model: Mapped[str] = mapped_column(String, default="")
    task_count: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd_costed: Mapped[float] = mapped_column(Float, default=0.0)
    cost_usd_estimated: Mapped[float] = mapped_column(Float, default=0.0)
    uncosted_count: Mapped[int] = mapped_column(Integer, default=0)
    # run-time (agent_task terminais com started_at+finished_at no bucket)
    run_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    run_task_count: Mapped[int] = mapped_column(Integer, default=0)
    run_failed_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


# ── Skills ────────────────────────────────────────────────────────────
class Skill(Base, TimestampMixin):
    __tablename__ = "skill"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")  # markdown
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)


class SkillFile(Base, TimestampMixin):
    """Arquivo de suporte de uma skill (multica 008 skill_file)."""

    __tablename__ = "skill_file"
    __table_args__ = (UniqueConstraint("skill_id", "path"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skill.id"), index=True)
    path: Mapped[str] = mapped_column(String)  # relativo ao diretório da skill
    content: Mapped[str] = mapped_column(Text, default="")


class SkillLabel(Base):
    """Associação label↔skill (multica 162 resource_labels / skill_to_label)."""

    __tablename__ = "skill_label"
    skill_id: Mapped[str] = mapped_column(ForeignKey("skill.id"), primary_key=True)
    label_id: Mapped[str] = mapped_column(ForeignKey("label.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


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
    # briefing operacional persistente (multica 084 squad.description / 088 squad.instructions)
    description: Mapped[str] = mapped_column(Text, default="")
    instructions: Mapped[str] = mapped_column(Text, default="")


class SquadMember(Base):
    __tablename__ = "squad_member"
    squad_id: Mapped[str] = mapped_column(ForeignKey("squad.id"), primary_key=True)
    member_type: Mapped[str] = mapped_column(String, primary_key=True)  # agent|member
    member_id: Mapped[str] = mapped_column(String, primary_key=True)
    # papel do membro dentro da squad (multica 084 squad_member.role)
    role: Mapped[str] = mapped_column(String, default="")


# ── Autopilots ────────────────────────────────────────────────────────
class Autopilot(Base, TimestampMixin):
    __tablename__ = "autopilot"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)  # espelho de status == active
    # ciclo de vida (multica 042): active|paused|archived
    status: Mapped[str] = mapped_column(String, default="active")
    # create_issue: run cria Issue; run_only: enfileira AgentTask direto (multica 042)
    execution_mode: Mapped[str] = mapped_column(String, default="create_issue")
    issue_title_template: Mapped[str | None] = mapped_column(String, nullable=True)
    # legado (single-trigger embutido) — triggers de verdade vivem em autopilot_trigger
    trigger_type: Mapped[str] = mapped_column(String, default="cron")  # cron|webhook|manual
    cron_expr: Mapped[str | None] = mapped_column(String, nullable=True)
    webhook_token: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    rule: Mapped[str] = mapped_column(Text, default="")  # instrução → vira issue
    target_agent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by_type: Mapped[str | None] = mapped_column(String, nullable=True)  # member|agent
    created_by_id: Mapped[str | None] = mapped_column(String, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AutopilotTrigger(Base, TimestampMixin):
    """Triggers múltiplos por autopilot (multica 042 autopilot_trigger)."""

    __tablename__ = "autopilot_trigger"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    autopilot_id: Mapped[str] = mapped_column(ForeignKey("autopilot.id"), index=True)
    kind: Mapped[str] = mapped_column(String)  # schedule|webhook|api
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    label: Mapped[str] = mapped_column(String, default="")
    cron_expression: Mapped[str | None] = mapped_column(String, nullable=True)
    timezone: Mapped[str] = mapped_column(String, default="UTC")
    webhook_token: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # verificação de assinatura no ingress (multica 093)
    provider: Mapped[str] = mapped_column(String, default="generic")  # generic|github
    signing_secret: Mapped[str | None] = mapped_column(String, nullable=True)
    # [{"event": "workflow_run", "actions": ["completed"]}] — NULL = aceita tudo (multica 110)
    event_filters: Mapped[list | None] = mapped_column(JSON, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # responsável atual pela config efetiva do trigger (multica 189)
    published_by_type: Mapped[str | None] = mapped_column(String, nullable=True)  # member|agent
    published_by_id: Mapped[str | None] = mapped_column(String, nullable=True)


class AutopilotRun(Base):
    __tablename__ = "autopilot_run"
    __table_args__ = (UniqueConstraint("trigger_id", "planned_at"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    autopilot_id: Mapped[str] = mapped_column(ForeignKey("autopilot.id"), index=True)
    status: Mapped[str] = mapped_column(String, default="running")  # running|done|failed|skipped
    issue_id: Mapped[str | None] = mapped_column(String, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    # enriquecimento (multica 042/079/124/186)
    trigger_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String, default="manual")  # schedule|manual|webhook|api
    task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    trigger_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # idempotência de dispatch agendado: horário canônico planejado (multica 124)
    planned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # versão da regra vigente no disparo (multica 186)
    rule_version_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AutopilotCollaborator(Base):
    """Grants explícitos de escrita (multica 128_autopilot_collaborator)."""

    __tablename__ = "autopilot_collaborator"
    autopilot_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_type: Mapped[str] = mapped_column(String, primary_key=True, default="member")
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    granted_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AutopilotSubscriber(Base):
    """Membros auto-inscritos nas issues geradas (multica 120_autopilot_subscriber)."""

    __tablename__ = "autopilot_subscriber"
    autopilot_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_type: Mapped[str] = mapped_column(String, primary_key=True, default="member")
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AutopilotRuleVersion(Base):
    """Snapshot append-only de publicações substantivas (multica 186)."""

    __tablename__ = "autopilot_rule_version"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    autopilot_id: Mapped[str] = mapped_column(String, index=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    published_by_type: Mapped[str] = mapped_column(String, default="member")  # member|agent|system
    published_by_id: Mapped[str | None] = mapped_column(String, nullable=True)
    config_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WebhookDelivery(Base):
    """Uma linha por POST aceito no ingress público (multica 093)."""

    __tablename__ = "webhook_delivery"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    autopilot_id: Mapped[str] = mapped_column(String, index=True)
    trigger_id: Mapped[str] = mapped_column(String, index=True)
    provider: Mapped[str] = mapped_column(String, default="generic")  # generic|github
    event: Mapped[str] = mapped_column(String, default="webhook.received")
    # github → X-GitHub-Delivery; generic → Idempotency-Key; NULL = sem dedupe
    dedupe_key: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    dedupe_source: Mapped[str | None] = mapped_column(String, nullable=True)
    signature_status: Mapped[str] = mapped_column(String, default="not_required")
    # not_required|valid|invalid|missing
    status: Mapped[str] = mapped_column(String, default="queued")
    # queued|dispatched|rejected|ignored|failed
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    selected_headers: Mapped[dict] = mapped_column(JSON, default=dict)
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_body: Mapped[str] = mapped_column(Text, default="")  # cap 256KiB no ingress
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str] = mapped_column(Text, default="")
    autopilot_run_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    replayed_from_delivery_id: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
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
    # unread/mark-read (multica 040_chat_unread_since + 151_chat_read_cursor)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unread_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChatDraftRestore(Base):
    """Cancelamento sem resposta: devolve o texto do usuário ao composer
    (multica 182/183 chat_draft_restore). id = id da ChatMessage removida."""

    __tablename__ = "chat_draft_restore"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    task_id: Mapped[str] = mapped_column(String, index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ChatPinnedAgent(Base):
    """Barra de agentes rápidos por usuário (multica 152/153 chat_pinned_agent)."""

    __tablename__ = "chat_pinned_agent"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", "agent_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    position: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


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


# ── Integrations: GitHub App ───────────────────────────────────────────
class GithubInstallation(Base, TimestampMixin):
    """Uma instalação do GitHub App vinculada a um workspace."""

    __tablename__ = "github_installation"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    installation_id: Mapped[str] = mapped_column(String, index=True, unique=True)
    account_login: Mapped[str] = mapped_column(String, default="")
    account_type: Mapped[str] = mapped_column(String, default="")  # User|Organization
    status: Mapped[str] = mapped_column(String, default="active")  # active|suspended|removed
    installed_by: Mapped[str | None] = mapped_column(String, nullable=True)


class GithubPullRequest(Base, TimestampMixin):
    """Espelho local de um PR GitHub (multica github_pull_request)."""

    __tablename__ = "github_pull_request"
    __table_args__ = (UniqueConstraint("installation_id", "repo_full_name", "number"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    installation_id: Mapped[str] = mapped_column(String, index=True)
    repo_full_name: Mapped[str] = mapped_column(String, index=True)  # owner/repo
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String, default="")
    state: Mapped[str] = mapped_column(String, default="open")  # open|draft|merged|closed
    draft: Mapped[bool] = mapped_column(Boolean, default=False)
    merged: Mapped[bool] = mapped_column(Boolean, default=False)
    head_sha: Mapped[str] = mapped_column(String, default="")
    head_ref: Mapped[str] = mapped_column(String, default="")
    base_ref: Mapped[str] = mapped_column(String, default="")
    mergeable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    author_login: Mapped[str] = mapped_column(String, default="")
    url: Mapped[str] = mapped_column(String, default="")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GithubCheckRun(Base):
    """Check run/suite de um PR (snapshot de CI, multica gi_check_run)."""

    __tablename__ = "github_check_run"
    __table_args__ = (UniqueConstraint("pull_request_id", "external_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    pull_request_id: Mapped[str] = mapped_column(String, index=True)
    external_id: Mapped[str] = mapped_column(String, default="")  # id do check_run/suite no GitHub
    name: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="queued")  # queued|in_progress|completed
    conclusion: Mapped[str | None] = mapped_column(String, nullable=True)
    # success|failure|neutral|cancelled|timed_out|action_required|skipped|stale
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class IssuePullRequest(Base):
    """Vínculo issue↔PR (multica issue_pull_request) — auto-link via texto
    ("closes RYU-123", "#123") ou vínculo manual; várias origens (github|vcs)."""

    __tablename__ = "issue_pull_request"
    __table_args__ = (UniqueConstraint("issue_id", "provider", "pull_request_ref"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    issue_id: Mapped[str] = mapped_column(String, index=True)
    provider: Mapped[str] = mapped_column(String, default="github")  # github|forgejo|gitea|gitlab
    pull_request_ref: Mapped[str] = mapped_column(String, index=True)  # id do GithubPullRequest/VcsPullRequest
    link_kind: Mapped[str] = mapped_column(String, default="auto")  # auto|manual
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ── Integrations: VCS self-hosted (Forgejo/Gitea/GitLab) ───────────────
class VcsConnection(Base, TimestampMixin):
    __tablename__ = "vcs_connection"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    provider: Mapped[str] = mapped_column(String)  # forgejo|gitea|gitlab
    base_url: Mapped[str] = mapped_column(String)
    repo: Mapped[str] = mapped_column(String)  # owner/repo (ou namespace/project no gitlab)
    access_token_enc: Mapped[str] = mapped_column(Text, default="")
    webhook_secret_enc: Mapped[str] = mapped_column(Text, default="")
    webhook_token: Mapped[str] = mapped_column(String, default="", index=True)  # segmento da URL do webhook
    status: Mapped[str] = mapped_column(String, default="active")  # active|error|disabled
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")


class VcsPullRequest(Base, TimestampMixin):
    """Espelho de PR/MR de VCS self-hosted (mesma forma do GithubPullRequest)."""

    __tablename__ = "vcs_pull_request"
    __table_args__ = (UniqueConstraint("connection_id", "number"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    connection_id: Mapped[str] = mapped_column(String, index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String, default="")
    state: Mapped[str] = mapped_column(String, default="open")
    draft: Mapped[bool] = mapped_column(Boolean, default=False)
    merged: Mapped[bool] = mapped_column(Boolean, default=False)
    head_sha: Mapped[str] = mapped_column(String, default="")
    url: Mapped[str] = mapped_column(String, default="")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── Integrations: Channels (Slack / Lark-Feishu) ───────────────────────
class ChannelInstallation(Base, TimestampMixin):
    """Instalação BYO de um canal de chat (Slack Socket Mode / Lark long-conn)."""

    __tablename__ = "channel_installation"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    channel_type: Mapped[str] = mapped_column(String, index=True)  # slack|lark
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    external_team_id: Mapped[str] = mapped_column(String, default="", index=True)
    external_team_name: Mapped[str] = mapped_column(String, default="")
    region: Mapped[str] = mapped_column(String, default="")  # lark: feishu|larksuite
    bot_token_enc: Mapped[str] = mapped_column(Text, default="")
    app_credential_enc: Mapped[str] = mapped_column(Text, default="")  # app-level token / app secret
    signing_secret_enc: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="active")  # active|disabled|error
    installed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")


class ChannelInboundDedup(Base):
    """Dedup de eventos inbound (Slack/Lark reenviam em timeout)."""

    __tablename__ = "channel_inbound_dedup"
    __table_args__ = (UniqueConstraint("channel_type", "installation_id", "external_event_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    channel_type: Mapped[str] = mapped_column(String, index=True)
    installation_id: Mapped[str] = mapped_column(String, index=True)
    external_event_id: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ChannelInboundAudit(Base):
    """Auditoria de toda mensagem inbound aceita (mesmo se ignorada depois)."""

    __tablename__ = "channel_inbound_audit"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    channel_type: Mapped[str] = mapped_column(String, index=True)
    installation_id: Mapped[str] = mapped_column(String, index=True)
    external_event_id: Mapped[str] = mapped_column(String, default="")
    external_channel_id: Mapped[str] = mapped_column(String, default="")
    external_user_id: Mapped[str] = mapped_column(String, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ChannelChatLink(Base, TimestampMixin):
    """Vínculo canal/thread ↔ chat_session, p/ conversa contínua com o agente."""

    __tablename__ = "channel_chat_link"
    __table_args__ = (
        UniqueConstraint("channel_type", "installation_id", "external_channel_id", "external_thread_id"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    channel_type: Mapped[str] = mapped_column(String, index=True)
    installation_id: Mapped[str] = mapped_column(String, index=True)
    external_channel_id: Mapped[str] = mapped_column(String, default="")
    external_thread_id: Mapped[str] = mapped_column(String, default="")
    chat_session_id: Mapped[str] = mapped_column(String, index=True)
    last_outbound_message_ts: Mapped[str] = mapped_column(String, default="")  # p/ update de card


class ChannelUserBinding(Base, TimestampMixin):
    """Vínculo usuário externo (Slack/Lark) ↔ conta Ryu, via token de uso único."""

    __tablename__ = "channel_user_binding"
    __table_args__ = (UniqueConstraint("channel_type", "installation_id", "external_user_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    channel_type: Mapped[str] = mapped_column(String, index=True)
    installation_id: Mapped[str] = mapped_column(String, index=True)
    external_user_id: Mapped[str] = mapped_column(String, index=True)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    bind_token: Mapped[str] = mapped_column(String, default="", index=True)
    bind_token_used: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
