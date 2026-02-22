import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import update

from app.config import settings
from app.database import async_session, init_db
from app.models import AppSetting, Scan
from app.routers import competitions, health, pages, scanner, sources
from app.services.geocoder import init_home_location
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
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
        # Load persisted home postcode from database
        saved_pc = await session.get(AppSetting, "home_postcode")
        if saved_pc:
            settings.home_postcode = saved_pc.value
            logger.info("Loaded home postcode from database: %s", saved_pc.value)
        await session.commit()
    await init_home_location()
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("Shutting down EquiCalendar")


app = FastAPI(title="EquiCalendar", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(health.router)
app.include_router(sources.router)
app.include_router(competitions.router)
app.include_router(scanner.router)
app.include_router(pages.router)
