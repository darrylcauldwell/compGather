from __future__ import annotations

import json
import logging
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Competition, Scan, Source
from app.parsers.registry import get_parser
from app.parsers.utils import normalise_venue_name
from app.services.geocoder import calculate_distance, geocode_postcode

logger = logging.getLogger(__name__)


async def run_scan(source_id: int, scan_id: int | None = None):
    """Run a scan for a single source."""
    async with async_session() as session:
        if scan_id:
            scan = await session.get(Scan, scan_id)
            scan.started_at = datetime.utcnow()
            scan.status = "running"
            await session.commit()
        else:
            scan = Scan(
                source_id=source_id,
                started_at=datetime.utcnow(),
                status="running",
            )
            session.add(scan)
            await session.commit()

        try:
            source = (
                await session.execute(
                    select(Source).where(Source.id == source_id, Source.enabled == True)
                )
            ).scalar_one_or_none()

            if not source:
                scan.status = "failed"
                scan.error = f"Source {source_id} not found or not enabled"
                scan.completed_at = datetime.utcnow()
            else:
                count = await _scan_source(session, source)
                scan.status = "completed"
                scan.competitions_found = count
                scan.completed_at = datetime.utcnow()
        except Exception as e:
            logger.exception("Scan failed for source %d", source_id)
            scan.status = "failed"
            scan.error = str(e)
            scan.completed_at = datetime.utcnow()

        await session.commit()
        logger.info("Scan %d finished: %s (%d found)", scan.id, scan.status, scan.competitions_found)


async def _scan_source(session: AsyncSession, source: Source) -> int:
    """Scan a single source: fetch → extract → upsert competitions."""
    logger.info("Scanning source: %s (%s) [parser: %s]", source.name, source.url, source.parser_key or "generic")

    parser = get_parser(source.parser_key)
    extracted = await parser.fetch_and_parse(source.url)

    count = 0
    for comp_data in extracted:
        try:
            date_start = date.fromisoformat(comp_data.date_start)
        except ValueError:
            logger.warning("Invalid date_start '%s', skipping", comp_data.date_start)
            continue

        date_end = None
        if comp_data.date_end:
            try:
                date_end = date.fromisoformat(comp_data.date_end)
            except ValueError:
                pass

        # Normalise venue name
        venue_name = normalise_venue_name(comp_data.venue_name)

        # Geocode venue
        lat, lng, distance = None, None, None
        if comp_data.venue_postcode:
            coords = await geocode_postcode(comp_data.venue_postcode)
            if coords:
                lat, lng = coords
                distance = calculate_distance(lat, lng)

        # Upsert: match on source + name + date + venue
        existing = (
            await session.execute(
                select(Competition).where(
                    Competition.source_id == source.id,
                    Competition.name == comp_data.name,
                    Competition.date_start == date_start,
                    Competition.venue_name == venue_name,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.last_seen_at = datetime.utcnow()
            existing.discipline = comp_data.discipline
            existing.has_pony_classes = comp_data.has_pony_classes
            existing.classes_raw = json.dumps(comp_data.classes)
            # Backfill fields that may have been missing on earlier runs
            if comp_data.url and not existing.url:
                existing.url = comp_data.url
            if comp_data.venue_postcode and not existing.venue_postcode:
                existing.venue_postcode = comp_data.venue_postcode
            if date_end and not existing.date_end:
                existing.date_end = date_end
            if lat is not None:
                existing.latitude = lat
                existing.longitude = lng
                existing.distance_miles = distance
        else:
            comp = Competition(
                source_id=source.id,
                name=comp_data.name,
                date_start=date_start,
                date_end=date_end,
                venue_name=venue_name,
                venue_postcode=comp_data.venue_postcode,
                latitude=lat,
                longitude=lng,
                distance_miles=distance,
                discipline=comp_data.discipline,
                has_pony_classes=comp_data.has_pony_classes,
                classes_raw=json.dumps(comp_data.classes),
                url=comp_data.url,
                raw_extract=json.dumps(comp_data.model_dump()),
            )
            session.add(comp)
            count += 1

    source.last_scanned_at = datetime.utcnow()
    await session.commit()
    logger.info("Source '%s': %d new competitions", source.name, count)
    return count
