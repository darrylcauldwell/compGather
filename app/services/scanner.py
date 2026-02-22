from __future__ import annotations

import json
import logging
from datetime import date, datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Competition, Scan, Source, Venue
from app.parsers.registry import get_parser
from app.parsers.utils import normalise_discipline, normalise_venue_name
from app.services.geocoder import _coords_in_uk, calculate_distance, geocode_postcode

logger = logging.getLogger(__name__)


def _validate_url(url: str | None) -> str | None:
    """Return the URL if it uses http(s), otherwise None."""
    if url and url.strip().lower().startswith(("http://", "https://")):
        return url.strip()
    if url:
        logger.warning("Rejected non-HTTP URL: %.100s", url)
    return None


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

        # Post-scan: check for significant drop in competition count
        if scan.status == "completed" and source_id:
            try:
                await _check_scan_threshold(session, source_id, scan)
            except Exception as e:
                logger.warning("Scan threshold check failed: %s", e)

        # Post-scan: backfill missing venue data from sibling events
        try:
            await _backfill_venue_data(session)
        except Exception as e:
            logger.warning("Venue backfill failed: %s", e)


async def _check_scan_threshold(
    session: AsyncSession, source_id: int, current_scan: Scan
) -> None:
    """Warn if this scan found significantly fewer competitions than the previous one."""
    prev = (
        await session.execute(
            select(Scan)
            .where(
                Scan.source_id == source_id,
                Scan.status == "completed",
                Scan.id != current_scan.id,
            )
            .order_by(Scan.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if not prev or prev.competitions_found == 0:
        return

    current = current_scan.competitions_found
    previous = prev.competitions_found
    if current < previous * 0.5:
        source = await session.get(Source, source_id)
        source_name = source.name if source else f"id={source_id}"
        logger.warning(
            "Source '%s' returned %d competitions, down from %d (previous scan) — "
            "possible parser issue",
            source_name, current, previous,
        )


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

        # Validate URL
        safe_url = _validate_url(comp_data.url)

        # Normalise venue name
        venue_name = normalise_venue_name(comp_data.venue_name)

        # Normalise discipline
        discipline, is_competition = normalise_discipline(comp_data.discipline)

        # Resolve venue coordinates: venues table → parser → postcode API
        lat, lng, distance = await _resolve_venue_coords(
            session, venue_name, comp_data.venue_postcode,
            comp_data.latitude, comp_data.longitude,
        )

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
            existing.discipline = discipline
            existing.is_competition = is_competition
            existing.has_pony_classes = comp_data.has_pony_classes
            # Always update URL if parser provides one
            if safe_url:
                existing.url = safe_url
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
                discipline=discipline,
                is_competition=is_competition,
                has_pony_classes=comp_data.has_pony_classes,
                url=safe_url,
                raw_extract=json.dumps(comp_data.model_dump()),
            )
            session.add(comp)
            count += 1

    source.last_scanned_at = datetime.utcnow()
    await session.commit()
    logger.info("Source '%s': %d new competitions", source.name, count)
    return count


async def _resolve_venue_coords(
    session: AsyncSession,
    venue_name: str,
    postcode: str | None,
    parser_lat: float | None,
    parser_lng: float | None,
) -> tuple[float | None, float | None, float | None]:
    """Resolve coordinates for a venue, checking the venues table first.

    Priority: 1) venues table  2) parser-provided coords  3) postcode geocode.
    Stores new results back into the venues table for future lookups.
    """
    lat, lng, distance = None, None, None

    # 1. Check the venues table
    if venue_name:
        venue = (
            await session.execute(
                select(Venue).where(Venue.name == venue_name)
            )
        ).scalar_one_or_none()

        if venue and venue.latitude is not None and _coords_in_uk(venue.latitude, venue.longitude):
            lat, lng = venue.latitude, venue.longitude
            distance = calculate_distance(lat, lng)
            # Update venue postcode if we have a better one
            if postcode and not venue.postcode:
                venue.postcode = postcode
            return lat, lng, distance

    # 2. Parser-provided coordinates (must be within UK bounds)
    if parser_lat is not None and parser_lng is not None and _coords_in_uk(parser_lat, parser_lng):
        lat, lng = parser_lat, parser_lng
        distance = calculate_distance(lat, lng)

    # 3. Geocode from postcode
    elif postcode:
        coords = await geocode_postcode(postcode)
        if coords:
            lat, lng = coords
            distance = calculate_distance(lat, lng)

    # Store in venues table for future lookups
    if venue_name and lat is not None:
        venue = (
            await session.execute(
                select(Venue).where(Venue.name == venue_name)
            )
        ).scalar_one_or_none()

        if venue:
            if venue.latitude is None:
                venue.latitude = lat
                venue.longitude = lng
            if postcode and not venue.postcode:
                venue.postcode = postcode
        else:
            session.add(Venue(
                name=venue_name,
                postcode=postcode,
                latitude=lat,
                longitude=lng,
            ))

    return lat, lng, distance


async def audit_disciplines(session: AsyncSession) -> None:
    """Audit and normalise discipline values across all competitions.

    Logs warnings for unmapped values and auto-fixes known mappings.
    """
    rows = (
        await session.execute(
            select(Competition.discipline, func.count(Competition.id))
            .where(Competition.discipline != None)
            .group_by(Competition.discipline)
        )
    ).all()

    fixed = 0
    for raw_disc, count in rows:
        canonical, is_comp = normalise_discipline(raw_disc)
        if canonical != raw_disc:
            logger.info(
                "Discipline audit: '%s' (%d records) → '%s'",
                raw_disc, count, canonical,
            )
            comps = (
                await session.execute(
                    select(Competition).where(Competition.discipline == raw_disc)
                )
            ).scalars().all()
            for comp in comps:
                comp.discipline = canonical
                comp.is_competition = is_comp
                fixed += 1
        elif canonical and canonical not in {
            "Show Jumping", "Dressage", "Eventing", "Cross Country",
            "Combined Training", "Showing", "Hunter Trial", "Pony Club",
            "NSEA", "Agricultural Show", "Endurance", "Gymkhana", "Other",
            "Venue Hire", "Training",
        }:
            logger.warning(
                "Unmapped discipline found: '%s' (%d records)", raw_disc, count
            )

    if fixed:
        await session.commit()
        logger.info("Discipline audit: fixed %d records", fixed)
    else:
        logger.info("Discipline audit: all values canonical")


async def _backfill_venue_data(session: AsyncSession) -> None:
    """Propagate coordinates and postcodes across events at the same venue.

    If any event at a venue has lat/lng, all events at that venue get the same
    coordinates, distance, and postcode. Runs after every scan.
    """
    # Find venues that have some events with coords and some without
    venues_with_gaps = (
        await session.execute(
            select(Competition.venue_name)
            .where(Competition.latitude == None)
            .where(
                Competition.venue_name.in_(
                    select(distinct(Competition.venue_name))
                    .where(Competition.latitude != None)
                )
            )
            .group_by(Competition.venue_name)
        )
    ).scalars().all()

    if not venues_with_gaps:
        return

    filled_coords = 0
    filled_pc = 0

    for venue_name in venues_with_gaps:
        # Get coords from an existing event at this venue
        donor = (
            await session.execute(
                select(Competition)
                .where(
                    Competition.venue_name == venue_name,
                    Competition.latitude != None,
                )
                .limit(1)
            )
        ).scalar_one_or_none()

        if not donor:
            continue

        # Update events missing coords
        missing = (
            await session.execute(
                select(Competition).where(
                    Competition.venue_name == venue_name,
                    Competition.latitude == None,
                )
            )
        ).scalars().all()

        for comp in missing:
            comp.latitude = donor.latitude
            comp.longitude = donor.longitude
            comp.distance_miles = calculate_distance(donor.latitude, donor.longitude)
            filled_coords += 1
            if donor.venue_postcode and not comp.venue_postcode:
                comp.venue_postcode = donor.venue_postcode
                filled_pc += 1

    if filled_coords:
        await session.commit()
        logger.info(
            "Venue backfill: %d events got coordinates, %d got postcodes",
            filled_coords, filled_pc,
        )
