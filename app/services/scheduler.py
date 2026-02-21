import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import Scan, Source
from app.services.scanner import run_scan

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler():
    """Start the daily scan scheduler."""
    hour, minute = settings.scan_schedule.split(":")
    scheduler.add_job(
        _run_scan_job,
        "cron",
        hour=int(hour),
        minute=int(minute),
        id="daily_scan",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started: daily scan at %s", settings.scan_schedule)


def stop_scheduler():
    """Shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


async def _run_scan_job():
    """Scheduled scan: create one scan record per enabled source."""
    logger.info("Scheduled scan starting")
    async with async_session() as session:
        result = await session.execute(select(Source).where(Source.enabled == True))
        sources = result.scalars().all()

        for source in sources:
            scan = Scan(source_id=source.id, status="pending")
            session.add(scan)
        await session.commit()

        for source in sources:
            # Get the scan we just created for this source
            scan_result = await session.execute(
                select(Scan).where(
                    Scan.source_id == source.id, Scan.status == "pending"
                ).order_by(Scan.id.desc()).limit(1)
            )
            scan = scan_result.scalar_one_or_none()
            if scan:
                await run_scan(source.id, scan_id=scan.id)

    logger.info("Scheduled scan complete for %d sources", len(sources))
