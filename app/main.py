import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from pythonjsonlogger import jsonlogger
from sqlalchemy import update

from app.config import settings
from app.database import async_session, init_db
from app.models import Scan
from app.routers import competitions, health, pages, scanner, sources
from app.services.scanner import (
    audit_venue_health,
    geocode_missing_venues,
    seed_aliases_from_seeds,
    seed_all_venues_from_seeds,
    seed_disciplines,
    seed_sources,
    seed_venue_postcodes,
)
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.venue_matcher import backfill_tbc_venues, migrate_hardcoded_aliases

# Configure JSON structured logging for Loki
handler = logging.StreamHandler(sys.stdout)
formatter = jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
    rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
)
handler.setFormatter(formatter)
logging.root.handlers = [handler]
logging.root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

# Suppress verbose logs from external libraries
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("playwright").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting EquiCalendar")
    await init_db()
    # Mark any scans left "running" or "pending" from a previous crash as failed
    async with async_session() as session:
        result = await session.execute(
            update(Scan)
            .where(Scan.status.in_(["running", "pending"]))
            .values(status="failed", error="Interrupted by restart")
        )
        if result.rowcount:
            logger.info("Cleaned up %d stale scans from previous run", result.rowcount)
        await session.commit()
    await seed_sources()
    await seed_all_venues_from_seeds()
    await seed_aliases_from_seeds()
    await seed_disciplines()
    await seed_venue_postcodes()
    async with async_session() as session:
        await migrate_hardcoded_aliases(session)
    async with async_session() as session:
        await backfill_tbc_venues(session)
    await geocode_missing_venues()
    await audit_venue_health()
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("Shutting down EquiCalendar")


app = FastAPI(title="EquiCalendar", lifespan=lifespan)

# Add Prometheus metrics instrumentation
Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    excluded_handlers=["/health", "/metrics"],
).instrument(app).expose(app, endpoint="/metrics")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(health.router)
app.include_router(sources.router)
app.include_router(competitions.router)
app.include_router(competitions.geocode_router)
app.include_router(scanner.router)
app.include_router(pages.router)
