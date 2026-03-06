import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.metrics import SCHEDULER_LAST_RUN
from app.models import Scan, Source
from app.services.scanner import audit_disciplines, run_scan

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler():
    """Start the rolling scan scheduler and daily discipline audit."""
    # Rolling scan: pick one due source every N minutes
    scheduler.add_job(
        _run_next_scan,
        "interval",
        minutes=settings.scan_interval_minutes,
        id="rolling_scan",
        replace_existing=True,
    )

    # Daily discipline audit at the configured hour
    hour, minute = settings.scan_schedule.split(":")
    scheduler.add_job(
        _run_discipline_audit,
        "cron",
        hour=int(hour),
        minute=int(minute),
        id="daily_audit",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler started: rolling scan every %d min, audit at %s",
        settings.scan_interval_minutes,
        settings.scan_schedule,
    )


def stop_scheduler():
    """Shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


async def _run_next_scan():
    """Pick the source most overdue for scanning and run it."""
    SCHEDULER_LAST_RUN.set_to_current_time()
    cutoff = datetime.utcnow() - timedelta(hours=24)

    async with async_session() as session:
        # Find enabled source not scanned in last 24h, oldest first.
        # Sources never scanned (last_scanned_at IS NULL) come first.
        result = await session.execute(
            select(Source)
            .where(Source.enabled == True)
            .where(
                (Source.last_scanned_at == None) | (Source.last_scanned_at < cutoff)  # noqa: E711
            )
            .order_by(Source.last_scanned_at.asc().nulls_first())
            .limit(1)
        )
        source = result.scalar_one_or_none()

        if not source:
            logger.debug("No sources due for scanning")
            return

        # Check no existing pending/running scan for this source
        busy = await session.execute(
            select(Scan.id).where(
                Scan.source_id == source.id,
                Scan.status.in_(["pending", "running"]),
            )
        )
        if busy.scalar_one_or_none():
            logger.debug("Source %s already has a pending/running scan, skipping", source.name)
            return

        scan = Scan(source_id=source.id, status="pending")
        session.add(scan)
        await session.commit()
        scan_id = scan.id

    logger.info("Rolling scan: %s (last scanned %s)", source.name, source.last_scanned_at)
    await run_scan(source.id, scan_id=scan_id)


async def _run_discipline_audit():
    """Daily discipline audit and normalisation."""
    async with async_session() as session:
        try:
            await audit_disciplines(session)
            logger.info("Daily discipline audit complete")
        except Exception as e:
            logger.warning("Discipline audit failed: %s", e)
