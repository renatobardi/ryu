"""Testes das migrações leves do init_db: idempotência e visibilidade de erro real."""
from __future__ import annotations

import structlog


async def test_light_migrations_are_idempotent():
    """Rodar init_db duas vezes não levanta (colunas já existentes são ignoradas)."""
    from ryu.db import init_db

    await init_db()
    await init_db()


async def test_duplicate_column_stays_silent():
    from ryu.db import apply_light_migrations

    with structlog.testing.capture_logs() as logs:
        await apply_light_migrations(["ALTER TABLE issue ADD COLUMN project_id VARCHAR"])
    assert [entry for entry in logs if entry["log_level"] == "warning"] == []


async def test_real_migration_error_is_logged():
    """DDL que falha por motivo REAL (tabela inexistente) não pode passar em silêncio."""
    from ryu.db import apply_light_migrations

    with structlog.testing.capture_logs() as logs:
        await apply_light_migrations(["ALTER TABLE tabela_que_nao_existe ADD COLUMN x VARCHAR"])
    warnings = [entry for entry in logs if entry["log_level"] == "warning"]
    assert len(warnings) == 1
    assert warnings[0]["event"] == "light_migration_failed"
    assert "tabela_que_nao_existe" in warnings[0]["ddl"]
