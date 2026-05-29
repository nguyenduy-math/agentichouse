from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Phase 2 migration: add ml_score column to existing databases
        await conn.execute(
            text("ALTER TABLE fraud_analyses ADD COLUMN IF NOT EXISTS ml_score INTEGER")
        )


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
