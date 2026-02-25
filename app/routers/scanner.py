from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_api_key
from app.database import async_session, get_session
from app.models import Scan, Source
from app.schemas import ScanCreate, ScanOut
from app.services.scanner import run_scan

router = APIRouter(prefix="/api/scans", tags=["scans"])

# Limit concurrent background scans to avoid SQLite write-lock contention.
# Each scan does HTTP fetching (slow, I/O bound) then a DB commit; at most
# 8 running concurrently gives good throughput without overwhelming SQLite.
_scan_semaphore = asyncio.Semaphore(8)

# Track live asyncio Tasks by scan_id so they can be cancelled.
_running_tasks: dict[int, asyncio.Task] = {}


async def _run_with_semaphore(source_id: int, scan_id: int) -> None:
    try:
        async with _scan_semaphore:
            await run_scan(source_id, scan_id=scan_id)
    except asyncio.CancelledError:
        # Update scan record to reflect the cancellation
        async with async_session() as session:
            scan = await session.get(Scan, scan_id)
            if scan and scan.status in ("pending", "running"):
                scan.status = "cancelled"
                scan.error = "Cancelled by user"
                from datetime import datetime
                scan.completed_at = datetime.utcnow()
                await session.commit()
        raise
    finally:
        _running_tasks.pop(scan_id, None)


@router.post("", response_model=list[ScanOut], status_code=202, dependencies=[Depends(require_api_key)])
async def trigger_scan(data: ScanCreate, session: AsyncSession = Depends(get_session)):
    """Trigger a scan in the background and return immediately.

    If source_id is provided, scans that single source.
    If source_id is None, creates one scan per enabled source.
    Sources already running or pending are skipped to prevent compounding lock contention.
    """
    if data.source_id:
        source_ids = [data.source_id]
    else:
        result = await session.execute(select(Source.id).where(Source.enabled == True))
        source_ids = list(result.scalars().all())

    # Skip sources that already have an active (running/pending) scan
    busy_result = await session.execute(
        select(Scan.source_id).where(
            Scan.source_id.in_(source_ids),
            Scan.status.in_(["running", "pending"]),
        )
    )
    busy_ids = set(busy_result.scalars().all())
    source_ids = [sid for sid in source_ids if sid not in busy_ids]

    scans = []
    for sid in source_ids:
        scan = Scan(source_id=sid, status="pending")
        session.add(scan)
        scans.append(scan)
    await session.commit()
    for scan in scans:
        await session.refresh(scan)

    # Launch each scan in the background, capped by semaphore; track for cancellation
    for scan in scans:
        task = asyncio.create_task(_run_with_semaphore(scan.source_id, scan_id=scan.id))
        _running_tasks[scan.id] = task

    return scans


@router.post("/{scan_id}/cancel", dependencies=[Depends(require_api_key)])
async def cancel_scan(scan_id: int):
    """Cancel a pending or running scan."""
    task = _running_tasks.get(scan_id)
    if task and not task.done():
        task.cancel()
        return {"cancelled": True}
    raise HTTPException(status_code=404, detail="No active task found for this scan")


@router.get("", response_model=list[ScanOut])
async def list_scans(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Scan).order_by(Scan.started_at.desc()).limit(50))
    return result.scalars().all()


