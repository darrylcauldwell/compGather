from __future__ import annotations

import math
from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import asc, case, desc, distinct, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, selectinload

from app.config import settings
from app.database import get_session
from app.models import Competition, Scan, Source, Venue, VenueAlias
from app.services.tag_manager import deserialize_tags, get_tag_display_name

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["analytics_domain"] = settings.analytics_domain


def format_tags(tags_json: str | None) -> list[dict[str, str]]:
    """Convert tags JSON to list of {tag, display_name} dicts for template."""
    if not tags_json:
        return []
    tags = deserialize_tags(tags_json)
    return [{"tag": tag, "display": get_tag_display_name(tag)} for tag in tags]


templates.env.filters["format_tags"] = format_tags

router = APIRouter(tags=["pages"])


PER_PAGE = 50


def _has_value(v) -> bool:
    """Return True if a filter param has a meaningful value (non-empty string or non-empty list)."""
    if isinstance(v, list):
        return len(v) > 0
    return bool(v)


def _build_query_string(params: dict, remove: str | None = None, remove_value: str | None = None) -> str:
    """Build a query string from filter params, optionally removing one key or a single value from a list key."""
    pairs: list[tuple[str, str]] = []
    for k, v in params.items():
        if k == remove:
            if remove_value is not None and isinstance(v, list):
                # Remove just this one value from the list
                for item in v:
                    if item != remove_value:
                        pairs.append((k, item))
            # else: skip entirely (remove whole key)
            continue
        if isinstance(v, list):
            for item in v:
                pairs.append((k, item))
        elif v:
            pairs.append((k, v))
    return "?" + urlencode(pairs) if pairs else "/"


def _pagination_url(params: dict, page: int) -> str:
    """Build a pagination URL preserving all current filter params."""
    pairs: list[tuple[str, str]] = []
    for k, v in params.items():
        if isinstance(v, list):
            for item in v:
                pairs.append((k, item))
        elif v:
            pairs.append((k, v))
    if page > 1:
        pairs.append(("page", str(page)))
    return "?" + urlencode(pairs) if pairs else "/"


@router.get("/")
async def competitions_page(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    max_distance: str | None = Query(None),
    pony: str | None = Query(None),
    discipline: list[str] = Query([]),
    venue: list[str] = Query([]),
    tag: list[str] = Query([]),
    source: list[str] = Query([]),
    q: str | None = Query(None),
    sort: str | None = Query(None),
    event_type: str | None = Query(None),
    include_online: str | None = Query(None),
    page: int = Query(1, ge=1),
    session: AsyncSession = Depends(get_session),
):
    # Sortable columns mapping
    sort_columns = {
        "date": Competition.date_start,
        "name": Competition.name,
        "discipline": Competition.discipline,
        "venue": Venue.name,
        "distance": Venue.distance_miles,
    }

    # Parse sort parameter
    sort_col_name = "date"
    sort_dir = "asc"
    is_newest = False

    if sort == "newest":
        is_newest = True
    elif sort:
        parts = sort.rsplit("_", 1)
        if len(parts) == 2 and parts[0] in sort_columns and parts[1] in ("asc", "desc"):
            sort_col_name = parts[0]
            sort_dir = parts[1]

    # For date sorting, clamp date_start to today so multi-day events that
    # started in the past (but are still running) sort alongside today's events
    # instead of appearing at the very start/end with their historic start date.
    today_literal = literal(date.today().isoformat())
    effective_date = case(
        (Competition.date_start < today_literal, today_literal),
        else_=Competition.date_start,
    )

    # Always join Venue for filtering/sorting and eager-load the relationship
    base_opts = (
        select(Competition)
        .outerjoin(Venue, Competition.venue_id == Venue.id)
        .options(
            selectinload(Competition.source),
            contains_eager(Competition.venue),
        )
    )

    if is_newest:
        stmt = base_opts.order_by(desc(Competition.first_seen_at))
    elif sort_col_name == "distance":
        order_fn = asc if sort_dir == "asc" else desc
        stmt = base_opts.order_by(
            case((Venue.distance_miles == None, 1), else_=0),
            order_fn(sort_columns[sort_col_name]),
        )
    elif sort_col_name == "date":
        order_fn = asc if sort_dir == "asc" else desc
        stmt = base_opts.order_by(order_fn(effective_date))
    else:
        order_fn = asc if sort_dir == "asc" else desc
        stmt = base_opts.order_by(order_fn(sort_columns[sort_col_name]))

    max_dist_float = None
    if max_distance and max_distance.strip():
        try:
            max_dist_float = float(max_distance)
        except ValueError:
            pass

    # Default date_from to today so the initial view only shows future events
    if not date_from:
        date_from = date.today().isoformat()
    # Include multi-day events that started before date_from but haven't ended
    parsed_from = date.fromisoformat(date_from)
    stmt = stmt.where(or_(
        Competition.date_start >= parsed_from,
        Competition.date_end >= parsed_from,
    ))
    if date_to:
        stmt = stmt.where(Competition.date_start <= date.fromisoformat(date_to))
    if pony == "yes":
        stmt = stmt.where(Competition.has_pony_classes == True)
    elif pony == "no":
        stmt = stmt.where(Competition.has_pony_classes == False)
    # Filter by discipline(s)
    cleaned_disciplines = [d.strip() for d in discipline if d.strip()]
    if len(cleaned_disciplines) == 1:
        stmt = stmt.where(Competition.discipline == cleaned_disciplines[0])
    elif len(cleaned_disciplines) > 1:
        stmt = stmt.where(Competition.discipline.in_(cleaned_disciplines))
    # Filter by tag(s) - tags are stored as JSON strings, so we check if each tag is in the JSON
    cleaned_tags = [t.strip() for t in tag if t.strip()]
    if cleaned_tags:
        # Build OR condition: competition must have at least one of the selected tags
        tag_conditions = []
        for selected_tag in cleaned_tags:
            # Use LIKE to match the tag string within the JSON array
            tag_conditions.append(Competition.tags.like(f'%"{selected_tag}"%'))
        if tag_conditions:
            stmt = stmt.where(or_(*tag_conditions))
    # Filter by source(s) - filter by source.name
    cleaned_sources = [s.strip() for s in source if s.strip()]
    if cleaned_sources:
        if len(cleaned_sources) == 1:
            stmt = stmt.where(Source.name == cleaned_sources[0])
        else:
            stmt = stmt.where(Source.name.in_(cleaned_sources))
    if max_dist_float is not None:
        stmt = stmt.where(Venue.distance_miles <= max_dist_float)
        # When distance filtering is active, exclude online events by default unless include_online is explicitly "yes"
        if include_online != "yes":
            stmt = stmt.where(Venue.name != "Online")
    cleaned_venues = [v.strip() for v in venue if v.strip()]
    if len(cleaned_venues) == 1:
        stmt = stmt.where(Venue.name == cleaned_venues[0])
    elif len(cleaned_venues) > 1:
        stmt = stmt.where(Venue.name.in_(cleaned_venues))
    if q and q.strip():
        stmt = stmt.where(Competition.name.ilike(f"%{q.strip()}%"))

    # Filter by event type
    if event_type == "competitions":
        stmt = stmt.where(Competition.event_type == "competition")
    elif event_type == "training":
        stmt = stmt.where(Competition.event_type == "training")
    elif event_type == "venue_hire":
        stmt = stmt.where(Competition.event_type == "venue_hire")
    # "all" or missing: no filter (show everything)

    # Count total results for pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0
    total_pages = max(1, math.ceil(total / PER_PAGE))
    page = min(page, total_pages)

    # Apply pagination
    stmt = stmt.limit(PER_PAGE).offset((page - 1) * PER_PAGE)

    result = await session.execute(stmt)
    competitions = result.unique().scalars().all()

    # Group competitions by date for date separators.
    # Use effective_date (clamped to today) so past-started multi-day events
    # group under today instead of their historic start date.
    date_groups: list[tuple[date, list]] = []
    current_sort_value = sort or "date_asc"
    show_date_groups = current_sort_value in ("date_asc", "date_desc")
    today_date = date.today()
    if show_date_groups and competitions:
        current_date = None
        current_group: list = []
        for comp in competitions:
            eff = comp.date_start if comp.date_start >= today_date else today_date
            if eff != current_date:
                if current_group:
                    date_groups.append((current_date, current_group))
                current_date = eff
                current_group = [comp]
            else:
                current_group.append(comp)
        if current_group:
            date_groups.append((current_date, current_group))

    # Distinct values for filter dropdowns (only from competitions)
    venue_names_result = await session.execute(
        select(distinct(Venue.name))
        .select_from(Competition)
        .join(Venue, Competition.venue_id == Venue.id)
        .where(
            Competition.date_start >= date.today(),
            Competition.event_type == "competition",
            Venue.name != None,
            Venue.name != "",
            Venue.name.notin_(["Tbc", "TBC", "tbc", "Tba", "TBA"]),
        )
        .order_by(Venue.name)
    )
    venue_names = [v for (v,) in venue_names_result.all()]

    disciplines_result = await session.execute(
        select(distinct(Competition.discipline))
        .where(
            Competition.date_start >= date.today(),
            Competition.discipline != None,
        )
        .order_by(Competition.discipline)
    )
    disciplines = [d for (d,) in disciplines_result.all()]

    # Build current filter params dict for URL generation
    filter_params = {
        "date_from": date_from or "",
        "date_to": date_to or "",
        "max_distance": max_distance or "",
        "pony": pony or "",
        "discipline": cleaned_disciplines,
        "venue": cleaned_venues,
        "tag": cleaned_tags,
        "source": cleaned_sources,
        "q": q or "",
        "sort": sort or "",
        "event_type": event_type or "",
        "include_online": include_online or "",
    }

    # Build active filter chips: list of (label, url_without_this_filter)
    active_filters = []
    today_iso = date.today().isoformat()
    # Only show date_from chip if it's not today (since today is the default)
    if date_from and date_from != today_iso:
        active_filters.append(("From " + date_from, _build_query_string(filter_params, "date_from")))
    if date_to:
        active_filters.append(("Until " + date_to, _build_query_string(filter_params, "date_to")))
    for disc in cleaned_disciplines:
        active_filters.append((disc, _build_query_string(filter_params, "discipline", remove_value=disc)))
    for selected_tag in cleaned_tags:
        # Get the display name for the tag
        tag_display = get_tag_display_name(selected_tag)
        active_filters.append((tag_display, _build_query_string(filter_params, "tag", remove_value=selected_tag)))
    for selected_source in cleaned_sources:
        active_filters.append((selected_source, _build_query_string(filter_params, "source", remove_value=selected_source)))
    if max_distance:
        active_filters.append(("Within " + max_distance + " mi", _build_query_string(filter_params, "max_distance")))
    if pony == "yes":
        active_filters.append(("Pony: Yes", _build_query_string(filter_params, "pony")))
    elif pony == "no":
        active_filters.append(("Pony: No", _build_query_string(filter_params, "pony")))
    for v in cleaned_venues:
        active_filters.append((v, _build_query_string(filter_params, "venue", remove_value=v)))
    if q:
        active_filters.append(('"' + q + '"', _build_query_string(filter_params, "q")))
    if event_type and event_type != "all":
        type_labels = {"competitions": "Competitions only", "training": "Training only", "venue_hire": "Venue Hire only"}
        active_filters.append((type_labels.get(event_type, event_type), _build_query_string(filter_params, "event_type")))

    # Pagination URLs
    prev_url = _pagination_url(filter_params, page - 1) if page > 1 else None
    next_url = _pagination_url(filter_params, page + 1) if page < total_pages else None

    return templates.TemplateResponse(
        "competitions.html",
        {
            "request": request,
            "competitions": competitions,
            "date_from": date_from or "",
            "date_to": date_to or "",
            "max_distance": max_distance or "",
            "pony": pony or "",
            "discipline": cleaned_disciplines,
            "venue": cleaned_venues,
            "tag": cleaned_tags,
            "source": cleaned_sources,
            "q": q or "",
            "venue_names": venue_names,
            "disciplines": disciplines,
            "home_postcode": settings.home_postcode,
            "sort": sort or "date_asc",
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "active_filters": active_filters,
            "filter_count": len(active_filters),
            "date_groups": date_groups,
            "show_date_groups": show_date_groups,
            "prev_url": prev_url,
            "next_url": next_url,
            "today": today_iso,
            "event_type": event_type or "all",
            "include_online": include_online,
        },
    )


@router.get("/map")
async def map_page(request: Request):
    """Redirect old /map URL to /venues?view=map."""
    return RedirectResponse(url="/venues?view=map", status_code=302)


@router.get("/admin")
async def admin_page(request: Request, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Source).order_by(Source.name))
    sources = result.scalars().all()

    # Get latest scan per source
    latest_scan_ids = (
        select(func.max(Scan.id).label("id"))
        .group_by(Scan.source_id)
    ).subquery()
    latest_scans_result = await session.execute(
        select(Scan).where(Scan.id.in_(select(latest_scan_ids.c.id)))
    )
    latest_scans = {s.source_id: s for s in latest_scans_result.scalars().all()}

    # Get latest *successful* scan per source
    latest_ok_ids = (
        select(func.max(Scan.id).label("id"))
        .where(Scan.status == "completed")
        .group_by(Scan.source_id)
    ).subquery()
    latest_ok_result = await session.execute(
        select(Scan).where(Scan.id.in_(select(latest_ok_ids.c.id)))
    )
    latest_ok_scans = {s.source_id: s for s in latest_ok_result.scalars().all()}

    # Get total competition count per source (event_type=competition, future only)
    total_comp_result = await session.execute(
        select(Competition.source_id, func.count(Competition.id))
        .where(
            Competition.date_start >= date.today(),
            Competition.event_type == "competition",
        )
        .group_by(Competition.source_id)
    )
    total_comp_counts = dict(total_comp_result.all())

    # Get total training count per source (training + venue_hire, future only)
    total_training_result = await session.execute(
        select(Competition.source_id, func.count(Competition.id))
        .where(
            Competition.date_start >= date.today(),
            Competition.event_type.in_(["training", "venue_hire"]),
        )
        .group_by(Competition.source_id)
    )
    total_training_counts = dict(total_training_result.all())

    return templates.TemplateResponse(
        "sources.html", {
            "request": request,
            "sources": sources,
            "latest_scans": latest_scans,
            "latest_ok_scans": latest_ok_scans,
            "total_comp_counts": total_comp_counts,
            "total_training_counts": total_training_counts,
        }
    )


@router.get("/venues")
async def venues_page(
    request: Request,
    sort: str | None = Query(None),
    view: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    # Parse sort parameter (format: "column_direction", e.g. "name_asc")
    sort_col = "name"
    sort_dir = "asc"

    if sort:
        parts = sort.rsplit("_", 1)
        if len(parts) == 2 and parts[0] in ("name", "postcode", "distance", "competitions") and parts[1] in ("asc", "desc"):
            sort_col = parts[0]
            sort_dir = parts[1]

    # Base query
    base_query = select(Venue)

    # Apply sorting
    if sort_col == "name":
        order_fn = asc if sort_dir == "asc" else desc
        base_query = base_query.order_by(order_fn(Venue.name))
    elif sort_col == "postcode":
        order_fn = asc if sort_dir == "asc" else desc
        base_query = base_query.order_by(order_fn(Venue.postcode))
    elif sort_col == "distance":
        order_fn = asc if sort_dir == "asc" else desc
        base_query = base_query.order_by(
            case((Venue.distance_miles == None, 1), else_=0),
            order_fn(Venue.distance_miles)
        )
    else:
        base_query = base_query.order_by(Venue.name)

    all_venues = (await session.execute(base_query)).scalars().all()

    # Competition count per venue_id
    comp_counts_result = await session.execute(
        select(Competition.venue_id, func.count(Competition.id))
        .where(Competition.venue_id != None)
        .group_by(Competition.venue_id)
    )
    comp_counts = dict(comp_counts_result.all())

    # Get competition URLs for venues with 1-5 competitions (for linking to events)
    venue_comp_links = {}
    for venue_id, count in comp_counts.items():
        if 1 <= count <= 5:
            comp_results = await session.execute(
                select(Competition.id, Competition.url)
                .where(Competition.venue_id == venue_id)
                .order_by(Competition.date_start)
            )
            links = [{"id": cid, "url": url} for cid, url in comp_results.all()]
            if links:
                venue_comp_links[venue_id] = links

    # Get aliases for each venue
    aliases_result = await session.execute(
        select(VenueAlias.venue_id, VenueAlias.alias)
        .order_by(VenueAlias.venue_id, VenueAlias.alias)
    )
    venue_aliases = {}
    for venue_id, alias_name in aliases_result.all():
        if venue_id not in venue_aliases:
            venue_aliases[venue_id] = []
        venue_aliases[venue_id].append(alias_name)

    # For each venue, determine its source/parser
    venue_details = {}
    for venue in all_venues:
        parser_sources = []
        if venue.source == "dynamic":
            sources_result = await session.execute(
                select(distinct(Source.name))
                .select_from(Competition)
                .join(Source, Competition.source_id == Source.id)
                .where(Competition.venue_id == venue.id)
                .order_by(Source.name)
            )
            parser_sources = [s for (s,) in sources_result.all()]

        venue_details[venue.id] = {
            "parser_sources": parser_sources,
        }

    # Apply competitions count sorting if needed
    venues = list(all_venues)
    if sort_col == "competitions":
        venues = sorted(
            venues,
            key=lambda v: comp_counts.get(v.id, 0),
            reverse=(sort_dir == "desc")
        )

    # Map data: aggregate venues with upcoming events and coordinates
    today = date.today()
    map_stmt = (
        select(
            Venue.id,
            Venue.name,
            Venue.postcode,
            Venue.latitude,
            Venue.longitude,
            Venue.distance_miles,
            func.count(Competition.id).label("event_count"),
            func.group_concat(distinct(Competition.discipline)).label("disciplines"),
        )
        .select_from(Venue)
        .join(Competition, Competition.venue_id == Venue.id)
        .where(
            Competition.date_start >= today,
            Venue.latitude != None,
            Venue.longitude != None,
        )
        .group_by(Venue.id)
    )
    map_result = await session.execute(map_stmt)
    map_rows = map_result.all()

    venues_json = []
    for row in map_rows:
        disciplines = []
        if row.disciplines:
            disciplines = [d.strip() for d in row.disciplines.split(",") if d.strip()]
        venues_json.append({
            "id": row.id,
            "name": row.name,
            "postcode": row.postcode or "",
            "lat": row.latitude,
            "lng": row.longitude,
            "distance_miles": round(row.distance_miles, 1) if row.distance_miles else None,
            "event_count": row.event_count,
            "disciplines": disciplines,
        })

    active_view = view if view in ("map", "table") else "map"

    return templates.TemplateResponse(
        "venues.html", {
            "request": request,
            "venues": venues,
            "comp_counts": comp_counts,
            "venue_details": venue_details,
            "venue_aliases": venue_aliases,
            "venue_comp_links": venue_comp_links,
            "sort": sort or "name_asc",
            "venues_json": venues_json,
            "active_view": active_view,
        }
    )




@router.get("/sources")
async def sources_redirect(request: Request):
    """Redirect old /sources URL to /admin."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/admin", status_code=302)


@router.get("/scans")
async def scans_redirect(request: Request):
    """Redirect old /scans URL to /admin."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/admin", status_code=302)
