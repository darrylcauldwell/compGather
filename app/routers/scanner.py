from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_api_key
from app.database import get_session
from app.models import Scan, Source
from app.schemas import ScanCreate, ScanOut
from app.services.scanner import run_scan

router = APIRouter(prefix="/api/scans", tags=["scans"])


@router.post("", response_model=list[ScanOut], status_code=202, dependencies=[Depends(require_api_key)])
async def trigger_scan(data: ScanCreate, session: AsyncSession = Depends(get_session)):
    """Trigger a scan in the background and return immediately.

    If source_id is provided, scans that single source.
    If source_id is None, creates one scan per enabled source.
    """
    if data.source_id:
        source_ids = [data.source_id]
    else:
        result = await session.execute(select(Source.id).where(Source.enabled == True))
        source_ids = list(result.scalars().all())

    scans = []
    for sid in source_ids:
        scan = Scan(source_id=sid, status="pending")
        session.add(scan)
        scans.append(scan)
    await session.commit()
    for scan in scans:
        await session.refresh(scan)

    # Launch each scan in the background
    for scan in scans:
        asyncio.create_task(run_scan(scan.source_id, scan_id=scan.id))

    return scans


@router.get("", response_model=list[ScanOut])
async def list_scans(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Scan).order_by(Scan.started_at.desc()).limit(50))
    return result.scalars().all()
