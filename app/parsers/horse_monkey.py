from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime

import httpx

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, infer_discipline, is_future_event
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

SEARCH_URL = "https://horsemonkey.com/uk/search"
DETAIL_URL = "https://horsemonkey.com/uk/equestrian_event/{id}"

# Only fetch competitions (type 1), skip memberships/educational/other
COMPETITION_TYPE_ID = 1
PER_PAGE = 100


@register_parser("horse_monkey")
class HorseMonkeyParser(BaseParser):
    """Parser for horsemonkey.com — uses the JSON search API.

    The search page is a Vue.js SPA backed by a POST JSON API.
    Sending X-Requested-With: XMLHttpRequest returns JSON instead of HTML.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
        limits = httpx.Limits(max_connections=15, max_keepalive_connections=10)
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=30.0, headers=headers, limits=limits
        ) as client:
            # Phase 1: Fetch all competition events from the search API
            all_rows = await self._fetch_all_events(client, date.today())
            logger.info("Horse Monkey: %d competition events from API", len(all_rows))

            # Phase 2: Build competitions from API data
            competitions: list[ExtractedCompetition] = []
            seen: set[int] = set()

            for row in all_rows:
                event_id = row.get("id")
                if not event_id or event_id in seen:
                    continue
                seen.add(event_id)

                comp = self._row_to_competition(row)
                if comp:
                    competitions.append(comp)

            # Phase 3: Enrich with coordinates from detail pages
            # Cache per venue — only need one detail page fetch per unique venue
            venue_coords: dict[str, tuple[float, float] | None] = {}
            venue_to_comps: dict[str, list[ExtractedCompetition]] = {}
            for c in competitions:
                if c.latitude is None:
                    venue_to_comps.setdefault(c.venue_name, []).append(c)

            # Pick one representative event per venue for fetching
            to_fetch: list[ExtractedCompetition] = []
            for venue, comps in venue_to_comps.items():
                to_fetch.append(comps[0])

            if to_fetch:
                logger.info(
                    "Horse Monkey: enriching %d venues (%d events) with detail pages",
                    len(to_fetch), sum(len(v) for v in venue_to_comps.values()),
                )
                sem = asyncio.Semaphore(5)

                async def _fetch_venue_coords(comp: ExtractedCompetition) -> None:
                    async with sem:
                        try:
                            await self._enrich_from_detail(client, comp)
                            if comp.latitude is not None:
                                venue_coords[comp.venue_name] = (comp.latitude, comp.longitude)
                            else:
                                venue_coords[comp.venue_name] = None
                        except Exception as e:
                            logger.debug(
                                "Horse Monkey: detail enrich failed for %s: %s",
                                comp.url, e,
                            )
                            venue_coords[comp.venue_name] = None

                await asyncio.gather(*[_fetch_venue_coords(c) for c in to_fetch])

                # Apply cached coords to all events at each venue
                for venue, comps in venue_to_comps.items():
                    coords = venue_coords.get(venue)
                    if coords:
                        for c in comps:
                            c.latitude, c.longitude = coords

                enriched = sum(1 for c in competitions if c.latitude is not None)
                logger.info("Horse Monkey: %d/%d events have coordinates", enriched, len(competitions))

        logger.info("Horse Monkey: extracted %d competitions", len(competitions))
        return competitions

    async def _fetch_all_events(
        self, client: httpx.AsyncClient, today: "date"
    ) -> list[dict]:
        """Paginate through the search API to get all competition events."""
        all_rows: list[dict] = []
        page = 1

        while True:
            payload = {
                "params": {
                    "filter": [
                        {"field": "order_by", "value": "start_asc", "type": "dropdown"},
                        {
                            "field": "events.event_type_id",
                            "value": [COMPETITION_TYPE_ID],
                            "type": "multiselect",
                        },
                        {
                            "field": "events.start",
                            "value": today.isoformat(),
                            "type": "date",
                        },
                    ],
                    "currentPage": page,
                    "perPage": PER_PAGE,
                    "sortBy": "start",
                    "sortDesc": False,
                }
            }

            resp = await client.post(SEARCH_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

            rows = data.get("rows", [])
            total = data.get("totalRows", 0)
            all_rows.extend(rows)

            logger.debug(
                "Horse Monkey: page %d — %d rows (total %d)", page, len(rows), total
            )

            if len(all_rows) >= total or not rows:
                break
            page += 1

            # Small delay to be respectful
            await asyncio.sleep(0.2)

        return all_rows

    def _row_to_competition(self, row: dict) -> ExtractedCompetition | None:
        """Convert a search API row to an ExtractedCompetition."""
        name = (row.get("name") or "").strip()
        start = row.get("start", "")
        end = row.get("end", "")

        if not name or not start:
            return None

        date_start = self._parse_datetime_to_date(start)
        date_end = self._parse_datetime_to_date(end)

        if not date_start:
            return None

        if not is_future_event(date_start, date_end):
            return None

        venue_name = (row.get("venue_name") or "").strip() or "TBC"
        disciplines = (row.get("disciplines") or "").strip()
        public_url = row.get("publicUrl", "")

        # Infer discipline and pony classes from name + discipline field
        text = f"{name} {disciplines}"
        discipline = infer_discipline(text) or disciplines or None
        has_pony = detect_pony_classes(text)

        return ExtractedCompetition(
            name=name,
            date_start=date_start,
            date_end=date_end if date_end != date_start else None,
            venue_name=venue_name,
            venue_postcode=None,  # Will be enriched from detail page
            discipline=discipline,
            has_pony_classes=has_pony,
            classes=[],
            url=public_url or f"https://horsemonkey.com/uk/equestrian_event/{row.get('id')}",
        )

    _LATLONG_RE = __import__("re").compile(
        r'"latitude":"(-?[\d.]+)","longitude":"(-?[\d.]+)"'
    )

    async def _enrich_from_detail(
        self, client: httpx.AsyncClient, comp: ExtractedCompetition
    ) -> None:
        """Fetch the event detail page and extract lat/lng from the embedded m_show JSON."""
        if not comp.url:
            return
        # Detail pages are normal HTML (no XHR header needed)
        resp = await client.get(
            comp.url,
            headers={"X-Requested-With": "", "Accept": "text/html"},
        )
        resp.raise_for_status()

        # The page embeds m_show: {"...","latitude":"53.056","longitude":"-1.368",...}
        m = self._LATLONG_RE.search(resp.text)
        if m:
            try:
                comp.latitude = float(m.group(1))
                comp.longitude = float(m.group(2))
            except (ValueError, TypeError):
                pass

    def _parse_datetime_to_date(self, dt_str: str) -> str | None:
        """Parse '2026-02-20 00:00:00' or '2026-02-20' to 'YYYY-MM-DD'."""
        if not dt_str:
            return None
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ"]:
            try:
                return datetime.strptime(dt_str.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None
