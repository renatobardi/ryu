import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

log = structlog.get_logger("ryu.db")

# Erros de ALTER TABLE que significam "a coluna já está lá" (sqlite/postgres):
# são o caso normal de re-execução, não falha.
_ALREADY_APPLIED = ("duplicate column", "already exists")


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with SessionLocal() as session:
        yield session


async def apply_light_migrations(ddls: list[str]) -> None:
    """Aplica ALTER TABLEs idempotentes; erro que não seja 'coluna já existe' vira log."""
    from sqlalchemy import text

    for ddl in ddls:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(ddl))
        except Exception as exc:  # noqa: BLE001
            message = str(exc).lower()
            if not any(marker in message for marker in _ALREADY_APPLIED):
                log.warning("light_migration_failed", ddl=ddl, error=str(exc)[:300])


async def init_db() -> None:
    from . import models  # noqa: F401  (registra todas as tabelas)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Migração leve p/ DBs existentes (create_all não altera tabelas já criadas)
    _light_migrations = [
        "ALTER TABLE issue ADD COLUMN project_id VARCHAR",
        "ALTER TABLE issue ADD COLUMN properties JSON",
        "ALTER TABLE comment ADD COLUMN resolved_at DATETIME",
        "ALTER TABLE comment ADD COLUMN resolved_by_type VARCHAR",
        "ALTER TABLE comment ADD COLUMN resolved_by_id VARCHAR",
        # agents-tasks ciclo 1 — agent
        "ALTER TABLE agent ADD COLUMN created_by VARCHAR",
        "ALTER TABLE agent ADD COLUMN visibility VARCHAR DEFAULT 'workspace'",
        "ALTER TABLE agent ADD COLUMN permission_mode VARCHAR DEFAULT 'public_to'",
        "ALTER TABLE agent ADD COLUMN archived_at DATETIME",
        "ALTER TABLE agent ADD COLUMN archived_by VARCHAR",
        "ALTER TABLE agent ADD COLUMN instructions TEXT DEFAULT ''",
        "ALTER TABLE agent ADD COLUMN model VARCHAR",
        "ALTER TABLE agent ADD COLUMN thinking_level VARCHAR",
        "ALTER TABLE agent ADD COLUMN service_tier VARCHAR",
        "ALTER TABLE agent ADD COLUMN profile_id VARCHAR",
        # agents-tasks ciclo 1 — agent_task (lease/retry/sessão/cancel)
        "ALTER TABLE agent_task ADD COLUMN attempt INTEGER DEFAULT 1",
        "ALTER TABLE agent_task ADD COLUMN max_attempts INTEGER DEFAULT 3",
        "ALTER TABLE agent_task ADD COLUMN retry_of_task_id VARCHAR",
        "ALTER TABLE agent_task ADD COLUMN rerun_of_task_id VARCHAR",
        "ALTER TABLE agent_task ADD COLUMN failure_reason VARCHAR",
        "ALTER TABLE agent_task ADD COLUMN session_id VARCHAR",
        "ALTER TABLE agent_task ADD COLUMN work_dir VARCHAR",
        "ALTER TABLE agent_task ADD COLUMN last_heartbeat_at DATETIME",
        "ALTER TABLE agent_task ADD COLUMN cancel_requested BOOLEAN DEFAULT 0",
        # agents-tasks ciclo 1 — task_message (transcript estruturado)
        "ALTER TABLE task_message ADD COLUMN seq INTEGER DEFAULT 0",
        "ALTER TABLE task_message ADD COLUMN type VARCHAR DEFAULT ''",
        "ALTER TABLE task_message ADD COLUMN tool VARCHAR DEFAULT ''",
        "ALTER TABLE task_message ADD COLUMN input JSON",
        "ALTER TABLE task_message ADD COLUMN output JSON",
        # chat-squads ciclo 1 — unread/read-cursor da sessão de chat
        "ALTER TABLE chat_session ADD COLUMN last_read_at DATETIME",
        "ALTER TABLE chat_session ADD COLUMN unread_since DATETIME",
        # chat-squads ciclo 1 — briefing persistente + papéis da squad
        "ALTER TABLE squad ADD COLUMN description TEXT DEFAULT ''",
        "ALTER TABLE squad ADD COLUMN instructions TEXT DEFAULT ''",
        "ALTER TABLE squad_member ADD COLUMN role VARCHAR DEFAULT ''",
        # daemon-cli ciclo 1 — claim por runtime externo
        "ALTER TABLE agent_task ADD COLUMN runtime_id VARCHAR",
        # autopilots-skills ciclo 1 — estados/execution_mode/template/criador
        "ALTER TABLE autopilot ADD COLUMN status VARCHAR DEFAULT 'active'",
        "ALTER TABLE autopilot ADD COLUMN execution_mode VARCHAR DEFAULT 'create_issue'",
        "ALTER TABLE autopilot ADD COLUMN issue_title_template VARCHAR",
        "ALTER TABLE autopilot ADD COLUMN created_by_type VARCHAR",
        "ALTER TABLE autopilot ADD COLUMN created_by_id VARCHAR",
        "ALTER TABLE autopilot ADD COLUMN last_run_at DATETIME",
        # autopilots-skills ciclo 1 — runs enriquecidas
        "ALTER TABLE autopilot_run ADD COLUMN trigger_id VARCHAR",
        "ALTER TABLE autopilot_run ADD COLUMN source VARCHAR DEFAULT 'manual'",
        "ALTER TABLE autopilot_run ADD COLUMN task_id VARCHAR",
        "ALTER TABLE autopilot_run ADD COLUMN completed_at DATETIME",
        "ALTER TABLE autopilot_run ADD COLUMN failure_reason VARCHAR",
        "ALTER TABLE autopilot_run ADD COLUMN trigger_payload JSON",
        "ALTER TABLE autopilot_run ADD COLUMN result JSON",
        "ALTER TABLE autopilot_run ADD COLUMN planned_at DATETIME",
        "ALTER TABLE autopilot_run ADD COLUMN rule_version_id VARCHAR",
        # autopilots-skills ciclo 1 — labels por namespace + skills
        "ALTER TABLE label ADD COLUMN resource_type VARCHAR DEFAULT 'issue'",
        "ALTER TABLE label ADD COLUMN description TEXT DEFAULT ''",
        "ALTER TABLE skill ADD COLUMN created_by VARCHAR",
        # workspace-auth ciclo 1 — workspace editável + hardening de auth + PAT
        "ALTER TABLE workspace ADD COLUMN description TEXT DEFAULT ''",
        "ALTER TABLE workspace ADD COLUMN context TEXT DEFAULT ''",
        "ALTER TABLE workspace ADD COLUMN settings JSON",
        "ALTER TABLE workspace ADD COLUMN repos JSON",
        "ALTER TABLE workspace ADD COLUMN avatar_url VARCHAR",
        "ALTER TABLE verification_code ADD COLUMN attempts INTEGER DEFAULT 0",
        "ALTER TABLE verification_code ADD COLUMN created_at DATETIME",
        "ALTER TABLE api_token ADD COLUMN token_prefix VARCHAR DEFAULT ''",
        "ALTER TABLE api_token ADD COLUMN last_used_at DATETIME",
        # usage-observability ciclo 1 — runtime dim + estimado/autoritativo
        "ALTER TABLE task_usage ADD COLUMN runtime VARCHAR DEFAULT ''",
        "ALTER TABLE task_usage ADD COLUMN costed BOOLEAN DEFAULT 1",
    ]
    await apply_light_migrations(_light_migrations)
