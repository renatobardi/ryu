from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from . import models  # noqa: F401  (registra todas as tabelas)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Migração leve p/ DBs existentes (create_all não altera tabelas já criadas)
    from sqlalchemy import text

    try:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE issue ADD COLUMN project_id VARCHAR"))
    except Exception:
        pass  # coluna já existe
