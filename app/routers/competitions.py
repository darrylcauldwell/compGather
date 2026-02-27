from __future__ import annotations

import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, selectinload

from app.database import get_session
from app.models import Competition, Venue
from app.schemas import CompetitionOut
from app.services.geocoder import geocode_postcode, reverse_geocode
from app.services.user_location import annotate_distances, get_user_coords

router = APIRouter(prefix="/api/competitions", tags=["competitions"])


@router.get("", response_model=list[CompetitionOut])
async def list_competitions(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    max_distance: float | None = Query(None),
    discipline: str | None = Query(None),
    postcode: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    user_coords = await get_user_coords(postcode)

    stmt = (
        select(Competition)
        .outerjoin(Venue, Competition.venue_id == Venue.id)
        .options(contains_eager(Competition.venue))
        .order_by(Competition.date_start)
    )

    if discipline and discipline.strip():
        stmt = stmt.where(Competition.discipline == discipline.strip())
    else:
        stmt = stmt.where(Competition.event_type == "competition")
    if date_from:
        # Include multi-day events that started before date_from but haven't ended
        stmt = stmt.where(or_(
            Competition.date_start >= date_from,
            Competition.date_end >= date_from,
        ))
    if date_to:
        stmt = stmt.where(Competition.date_start <= date_to)

    result = await session.execute(stmt)
    comps = list(result.unique().scalars().all())

    # Annotate distances per-request
    annotate_distances(comps, user_coords)

    # Apply distance filter in Python
    if max_distance is not None and user_coords:
        comps = [c for c in comps if c.distance_miles is not None and c.distance_miles <= max_distance]

    return comps


MAX_EXPORT = 200


@router.get("/export-ical")
async def export_ical(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    max_distance: float | None = Query(None),
    discipline: str | None = Query(None),
    venue: str | None = Query(None),
    postcode: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Download multiple competitions as a single .ics calendar file."""
    user_coords = await get_user_coords(postcode)

    stmt = (
        select(Competition)
        .outerjoin(Venue, Competition.venue_id == Venue.id)
        .options(contains_eager(Competition.venue))
        .order_by(Competition.date_start)
    )

    if discipline and discipline.strip():
        stmt = stmt.where(Competition.discipline == discipline.strip())
    else:
        stmt = stmt.where(Competition.event_type == "competition")

    if not date_from:
        date_from = date.today()
    # Include multi-day events that started before date_from but haven't ended
    stmt = stmt.where(or_(
        Competition.date_start >= date_from,
        Competition.date_end >= date_from,
    ))
    if date_to:
        stmt = stmt.where(Competition.date_start <= date_to)
    if venue and venue.strip():
        stmt = stmt.where(Venue.name.ilike(f"%{venue.strip()}%"))

    result = await session.execute(stmt)
    all_comps = list(result.unique().scalars().all())

    # Annotate distances and apply distance filter in Python
    annotate_distances(all_comps, user_coords)
    if max_distance is not None and user_coords:
        all_comps = [c for c in all_comps if c.distance_miles is not None and c.distance_miles <= max_distance]

    comps = all_comps[:MAX_EXPORT]

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
    result = await session.execute(
        select(Competition)
        .options(selectinload(Competition.venue))
        .where(Competition.id == competition_id)
    )
    comp = result.scalar_one_or_none()
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
    result = await session.execute(
        select(Competition)
        .options(selectinload(Competition.venue))
        .where(Competition.id == competition_id)
    )
    comp = result.scalar_one_or_none()
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


class GeolocateBody(BaseModel):
    lat: float
    lng: float


# --- Stateless geocode endpoints (no router prefix) ---
geocode_router = APIRouter(prefix="/api", tags=["geocode"])


@geocode_router.get("/geocode")
async def geocode_endpoint(postcode: str = Query(...)):
    """Validate and geocode a UK postcode. Returns {postcode, lat, lng} or 400."""
    coords = await geocode_postcode(postcode.strip())
    if not coords:
        raise HTTPException(400, "Invalid or unrecognised postcode")
    return {"postcode": postcode.strip().upper(), "lat": coords[0], "lng": coords[1]}


@geocode_router.post("/geocode/reverse")
async def reverse_geocode_endpoint(body: GeolocateBody):
    """Reverse geocode lat/lng to nearest UK postcode."""
    postcode = await reverse_geocode(body.lat, body.lng)
    if not postcode:
        raise HTTPException(400, "Could not determine a UK postcode for your location")
    return {"postcode": postcode.strip().upper()}
