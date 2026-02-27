import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"timeout": 30},  # wait up to 30s for SQLite write lock before failing
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Venue matching tables
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS venue_aliases ("
            "  id INTEGER PRIMARY KEY,"
            "  alias TEXT NOT NULL UNIQUE,"
            "  venue_id INTEGER NOT NULL REFERENCES venues(id),"
            "  source TEXT,"
            "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
            ")"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_venue_alias_alias "
            "ON venue_aliases(alias)"
        ))
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS venue_match_reviews ("
            "  id INTEGER PRIMARY KEY,"
            "  raw_name TEXT NOT NULL,"
            "  normalised_name TEXT NOT NULL,"
            "  candidate_venue_id INTEGER NOT NULL REFERENCES venues(id),"
            "  confidence REAL NOT NULL,"
            "  postcode TEXT,"
            "  parser_lat REAL,"
            "  parser_lng REAL,"
            "  status TEXT DEFAULT 'pending',"
            "  resolved_at DATETIME,"
            "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
            ")"
        ))

    # Venue FK migration: add distance_miles to venues, venue_id FK to competitions
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE venues ADD COLUMN distance_miles REAL"))
            logger.info("Migration: added distance_miles column to venues")
        except Exception:
            pass  # column already exists

        try:
            await conn.execute(
                text("ALTER TABLE competitions ADD COLUMN venue_id INTEGER REFERENCES venues(id)")
            )
            logger.info("Migration: added venue_id column to competitions")
        except Exception:
            pass  # column already exists

    # Venue match observability columns
    async with engine.begin() as conn:
        try:
            await conn.execute(
                text("ALTER TABLE competitions ADD COLUMN venue_match_type TEXT")
            )
            logger.info("Migration: added venue_match_type column to competitions")
        except Exception:
            pass  # column already exists

        try:
            await conn.execute(
                text("ALTER TABLE scans ADD COLUMN venue_match_summary TEXT")
            )
            logger.info("Migration: added venue_match_summary column to scans")
        except Exception:
            pass  # column already exists

    # Scan competition/training breakdown columns
    async with engine.begin() as conn:
        try:
            await conn.execute(
                text("ALTER TABLE scans ADD COLUMN competitions_found_comp INTEGER DEFAULT 0")
            )
            logger.info("Migration: added competitions_found_comp column to scans")
        except Exception:
            pass  # column already exists

        try:
            await conn.execute(
                text("ALTER TABLE scans ADD COLUMN competitions_found_training INTEGER DEFAULT 0")
            )
            logger.info("Migration: added competitions_found_training column to scans")
        except Exception:
            pass  # column already exists

    # Venue tracking columns (for data quality management)
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE venues ADD COLUMN source TEXT DEFAULT 'dynamic'"))
            logger.info("Migration: added source column to venues")
        except Exception as e:
            logger.debug(f"source column: {e}")

        try:
            await conn.execute(text("ALTER TABLE venues ADD COLUMN seed_batch TEXT"))
            logger.info("Migration: added seed_batch column to venues")
        except Exception as e:
            logger.debug(f"seed_batch column: {e}")

        try:
            await conn.execute(text("ALTER TABLE venues ADD COLUMN validation_source TEXT"))
            logger.info("Migration: added validation_source column to venues")
        except Exception as e:
            logger.debug(f"validation_source column: {e}")

        try:
            await conn.execute(text("ALTER TABLE venues ADD COLUMN confidence REAL"))
            logger.info("Migration: added confidence column to venues")
        except Exception as e:
            logger.debug(f"confidence column: {e}")

    # VenueAlias tracking column
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE venue_aliases ADD COLUMN origin TEXT DEFAULT 'dynamic'"))
            logger.info("Migration: added origin column to venue_aliases")
        except Exception:
            pass  # column already exists

    # Tags column for event classification
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE competitions ADD COLUMN tags TEXT"))
            logger.info("Migration: added tags column to competitions")
        except Exception:
            pass  # column already exists

    # event_type column: materialised from tags for fast filtering
    async with engine.begin() as conn:
        try:
            await conn.execute(
                text("ALTER TABLE competitions ADD COLUMN event_type TEXT DEFAULT 'competition'")
            )
            logger.info("Migration: added event_type column")
            # Backfill from existing is_competition + discipline
            await conn.execute(text(
                "UPDATE competitions SET event_type = 'training' "
                "WHERE is_competition = 0 AND discipline = 'Training'"
            ))
            await conn.execute(text(
                "UPDATE competitions SET event_type = 'venue_hire' "
                "WHERE is_competition = 0 AND discipline = 'Venue Hire'"
            ))
            await conn.execute(text(
                "UPDATE competitions SET event_type = 'training' "
                "WHERE is_competition = 0 AND event_type = 'competition'"
            ))
            logger.info("Migration: backfilled event_type from is_competition/discipline")
        except Exception:
            pass  # column already exists

    # Rename agricultural_show → show
    async with engine.begin() as conn:
        try:
            await conn.execute(text(
                "UPDATE competitions SET event_type = 'show' "
                "WHERE event_type = 'agricultural_show'"
            ))
            await conn.execute(text(
                "UPDATE competitions SET tags = REPLACE(tags, '\"type:agricultural-show\"', '\"type:show\"') "
                "WHERE tags LIKE '%type:agricultural-show%'"
            ))
            logger.info("Migration: renamed agricultural_show → show")
        except Exception:
            pass

    # Drop legacy has_pony_classes column (no longer in model)
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE competitions DROP COLUMN has_pony_classes"))
            logger.info("Migration: dropped legacy has_pony_classes column")
        except Exception:
            pass  # column already removed or doesn't exist

    # Performance indexes
    async with engine.begin() as conn:
        await conn.execute(text("DROP INDEX IF EXISTS idx_comp_date_active"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_comp_date_type "
            "ON competitions (date_start, event_type)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_comp_discipline "
            "ON competitions (discipline)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_comp_venue_id "
            "ON competitions (venue_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_venue_source "
            "ON venues (source)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_venue_confidence "
            "ON venues (confidence)"
        ))


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
