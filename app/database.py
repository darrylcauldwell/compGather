import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Lightweight migrations for SQLite — add columns that don't exist yet
    async with engine.begin() as conn:
        try:
            await conn.execute(
                text("ALTER TABLE competitions ADD COLUMN is_competition BOOLEAN DEFAULT 1")
            )
            logger.info("Migration: added is_competition column")
        except Exception:
            pass  # column already exists

    # Performance indexes
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_comp_date_active "
            "ON competitions (date_start, is_competition)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_comp_discipline "
            "ON competitions (discipline)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_comp_venue "
            "ON competitions (venue_name)"
        ))


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
