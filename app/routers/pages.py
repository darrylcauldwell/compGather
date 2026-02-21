from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_session
from app.models import Competition, Scan, Source
from app.parsers.registry import list_parser_keys

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(tags=["pages"])


@router.get("/")
async def competitions_page(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    max_distance: str | None = Query(None),
    pony: str | None = Query(None),
    discipline: str | None = Query(None),
    venue: str | None = Query(None),
    sort: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    # Sortable columns mapping
    sort_columns = {
        "date": Competition.date_start,
        "name": Competition.name,
        "discipline": Competition.discipline,
        "venue": Competition.venue_name,
        "distance": Competition.distance_miles,
    }

    # Parse sort parameter: "distance_asc" or "distance_desc"
    sort_col_name = "date"
    sort_dir = "asc"
    if sort:
        parts = sort.rsplit("_", 1)
        if len(parts) == 2 and parts[0] in sort_columns and parts[1] in ("asc", "desc"):
            sort_col_name = parts[0]
            sort_dir = parts[1]

    sort_column = sort_columns[sort_col_name]
    order_fn = asc if sort_dir == "asc" else desc

    # For distance sorting, put nulls last
    if sort_col_name == "distance":
        from sqlalchemy import case
        stmt = (
            select(Competition)
            .options(selectinload(Competition.source))
            .order_by(
                case((Competition.distance_miles == None, 1), else_=0),
                order_fn(sort_column),
            )
        )
    else:
        stmt = select(Competition).options(selectinload(Competition.source)).order_by(order_fn(sort_column))

    max_dist_float = None
    if max_distance and max_distance.strip():
        try:
            max_dist_float = float(max_distance)
        except ValueError:
            pass

    if date_from:
        stmt = stmt.where(Competition.date_start >= date.fromisoformat(date_from))
    if date_to:
        stmt = stmt.where(Competition.date_start <= date.fromisoformat(date_to))
    if pony == "yes":
        stmt = stmt.where(Competition.has_pony_classes == True)
    elif pony == "no":
        stmt = stmt.where(Competition.has_pony_classes == False)
    if discipline and discipline.strip():
        stmt = stmt.where(Competition.discipline == discipline.strip())
    if max_dist_float is not None:
        stmt = stmt.where(
            Competition.distance_miles != None,
            Competition.distance_miles <= max_dist_float,
        )
    if venue and venue.strip():
        stmt = stmt.where(Competition.venue_name.ilike(f"%{venue.strip()}%"))

    result = await session.execute(stmt)
    competitions = result.scalars().all()

    # Distinct values for filter dropdowns
    from sqlalchemy import func, distinct
    venue_names_result = await session.execute(
        select(distinct(Competition.venue_name))
        .where(Competition.date_start >= date.today())
        .order_by(Competition.venue_name)
    )
    venue_names = [v for (v,) in venue_names_result.all()]

    disciplines_result = await session.execute(
        select(distinct(Competition.discipline))
        .where(Competition.date_start >= date.today(), Competition.discipline != None)
        .order_by(Competition.discipline)
    )
    disciplines = [d for (d,) in disciplines_result.all()]

    return templates.TemplateResponse(
        "competitions.html",
        {
            "request": request,
            "competitions": competitions,
            "date_from": date_from or "",
            "date_to": date_to or "",
            "max_distance": max_distance or "",
            "pony": pony or "",
            "discipline": discipline or "",
            "venue": venue or "",
            "venue_names": venue_names,
            "disciplines": disciplines,
            "home_postcode": settings.home_postcode,
            "sort": sort or "date_asc",
        },
    )


@router.get("/sources")
async def sources_page(request: Request, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Source).order_by(Source.name))
    sources = result.scalars().all()

    # Get latest scan per source
    from sqlalchemy import func
    latest_scan_ids = (
        select(func.max(Scan.id).label("id"))
        .group_by(Scan.source_id)
    ).subquery()
    latest_scans_result = await session.execute(
        select(Scan).where(Scan.id.in_(select(latest_scan_ids.c.id)))
    )
    latest_scans = {s.source_id: s for s in latest_scans_result.scalars().all()}

    # Get future competition count per source
    comp_counts_result = await session.execute(
        select(Competition.source_id, func.count(Competition.id))
        .where(Competition.date_start >= date.today())
        .group_by(Competition.source_id)
    )
    comp_counts = dict(comp_counts_result.all())

    return templates.TemplateResponse(
        "sources.html", {
            "request": request,
            "sources": sources,
            "parser_keys": list_parser_keys(),
            "latest_scans": latest_scans,
            "comp_counts": comp_counts,
        }
    )


@router.get("/scans")
async def scans_page(request: Request):
    """Redirect /scans to /sources since they are now merged."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/sources", status_code=302)
