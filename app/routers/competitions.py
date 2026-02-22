from __future__ import annotations

import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.models import AppSetting, Competition
from app.schemas import CompetitionOut
from app.services.geocoder import calculate_distance, set_home_postcode

router = APIRouter(prefix="/api/competitions", tags=["competitions"])


@router.get("", response_model=list[CompetitionOut])
async def list_competitions(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    max_distance: float | None = Query(None),
    pony_only: bool = Query(False),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Competition).order_by(Competition.date_start)

    if date_from:
        stmt = stmt.where(Competition.date_start >= date_from)
    if date_to:
        stmt = stmt.where(Competition.date_start <= date_to)
    if pony_only:
        stmt = stmt.where(Competition.has_pony_classes == True)
    if max_distance is not None:
        stmt = stmt.where(
            Competition.distance_miles != None,
            Competition.distance_miles <= max_distance,
        )

    result = await session.execute(stmt)
    return result.scalars().all()


MAX_EXPORT = 200


@router.get("/export-ical")
async def export_ical(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    max_distance: float | None = Query(None),
    pony_only: bool = Query(False),
    discipline: str | None = Query(None),
    venue: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Download multiple competitions as a single .ics calendar file."""
    stmt = select(Competition).where(
        Competition.is_competition == True,
    ).order_by(Competition.date_start)

    if not date_from:
        date_from = date.today()
    stmt = stmt.where(Competition.date_start >= date_from)
    if date_to:
        stmt = stmt.where(Competition.date_start <= date_to)
    if pony_only:
        stmt = stmt.where(Competition.has_pony_classes == True)
    if max_distance is not None:
        stmt = stmt.where(
            Competition.distance_miles != None,
            Competition.distance_miles <= max_distance,
        )
    if discipline and discipline.strip():
        stmt = stmt.where(Competition.discipline == discipline.strip())
    if venue and venue.strip():
        stmt = stmt.where(Competition.venue_name.ilike(f"%{venue.strip()}%"))

    stmt = stmt.limit(MAX_EXPORT)
    result = await session.execute(stmt)
    comps = result.scalars().all()

    if not comps:
        raise HTTPException(404, "No competitions match the current filters")

    events = []
    for comp in comps:
        dtstart = comp.date_start.strftime("%Y%m%d")
        end_date = comp.date_end if comp.date_end else comp.date_start
        dtend = (end_date + timedelta(days=1)).strftime("%Y%m%d")

        location_parts = [comp.venue_name]
        if comp.venue_postcode:
            location_parts.append(comp.venue_postcode)
        location = _ical_escape(", ".join(location_parts))
        summary = _ical_escape(comp.name)
        url_line = f"URL:{comp.url}\r\n" if comp.url else ""
        uid = f"comp-{comp.id}@equicalendar"

        events.append(
            "BEGIN:VEVENT\r\n"
            f"UID:{uid}\r\n"
            f"DTSTART;VALUE=DATE:{dtstart}\r\n"
            f"DTEND;VALUE=DATE:{dtend}\r\n"
            f"SUMMARY:{summary}\r\n"
            f"LOCATION:{location}\r\n"
            f"{url_line}"
            "END:VEVENT\r\n"
        )

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//EquiCalendar//EN\r\n"
        + "".join(events)
        + "END:VCALENDAR\r\n"
    )

    return Response(
        content=ics,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="equicalendar-{len(comps)}-events.ics"',
        },
    )


@router.get("/{competition_id}", response_model=CompetitionOut)
async def get_competition(
    competition_id: int, session: AsyncSession = Depends(get_session)
):
    comp = await session.get(Competition, competition_id)
    if not comp:
        raise HTTPException(404, "Competition not found")
    return comp


def _ical_escape(text: str) -> str:
    """Escape text for iCalendar values (RFC 5545)."""
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\n", "\\n")
    return text


@router.get("/{competition_id}/ical")
async def competition_ical(
    competition_id: int, session: AsyncSession = Depends(get_session)
):
    """Download a single competition as an .ics calendar file."""
    comp = await session.get(Competition, competition_id)
    if not comp:
        raise HTTPException(404, "Competition not found")

    dtstart = comp.date_start.strftime("%Y%m%d")
    # DTEND for all-day events is exclusive, so add 1 day
    end_date = comp.date_end if comp.date_end else comp.date_start
    dtend = (end_date + timedelta(days=1)).strftime("%Y%m%d")

    location_parts = [comp.venue_name]
    if comp.venue_postcode:
        location_parts.append(comp.venue_postcode)
    location = _ical_escape(", ".join(location_parts))

    summary = _ical_escape(comp.name)
    url_line = f"URL:{comp.url}\r\n" if comp.url else ""

    uid = f"comp-{comp.id}@equicalendar"

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//EquiCalendar//EN\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTART;VALUE=DATE:{dtstart}\r\n"
        f"DTEND;VALUE=DATE:{dtend}\r\n"
        f"SUMMARY:{summary}\r\n"
        f"LOCATION:{location}\r\n"
        f"{url_line}"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )

    # Sanitise filename
    safe_name = re.sub(r"[^\w\s-]", "", comp.name)[:50].strip()
    safe_name = re.sub(r"\s+", "-", safe_name)

    return Response(
        content=ics,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}.ics"',
        },
    )


class PostcodeUpdate(BaseModel):
    postcode: str


@router.post("/update-postcode")
async def update_home_postcode(
    body: PostcodeUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update home postcode and recalculate all competition distances."""
    postcode = body.postcode.strip().upper()
    ok = await set_home_postcode(postcode)
    if not ok:
        raise HTTPException(400, "Invalid postcode")
    settings.home_postcode = postcode

    # Persist to database so it survives restarts
    existing = await session.get(AppSetting, "home_postcode")
    if existing:
        existing.value = postcode
    else:
        session.add(AppSetting(key="home_postcode", value=postcode))

    # Recalculate distances for all competitions with coordinates
    result = await session.execute(
        select(Competition).where(Competition.latitude != None)
    )
    comps = result.scalars().all()
    updated = 0
    for comp in comps:
        dist = calculate_distance(comp.latitude, comp.longitude)
        if dist is not None:
            comp.distance_miles = dist
            updated += 1
    await session.commit()

    return {"postcode": postcode, "distances_updated": updated}
