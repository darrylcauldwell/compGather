from __future__ import annotations

import asyncio
import logging
import re
from datetime import date

from app.parsers.bases import HttpParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, infer_discipline
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

SEARCH_URL = "https://horsemonkey.com/uk/search"
DETAIL_URL = "https://horsemonkey.com/uk/equestrian_event/{id}"

COMPETITION_TYPE_ID = 1
PER_PAGE = 100


@register_parser("horse_monkey")
class HorseMonkeyParser(HttpParser):
    """Parser for horsemonkey.com — uses the JSON search API.

    The search page is a Vue.js SPA backed by a POST JSON API.
    """

    HEADERS = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        import httpx
        limits = httpx.Limits(max_connections=15, max_keepalive_connections=10)
        async with self._make_client(limits=limits) as client:
            all_rows = await self._fetch_all_events(client, date.today())
            logger.info("Horse Monkey: %d competition events from API", len(all_rows))

            competitions: list[ExtractedEvent] = []
            seen: set[int] = set()

            for row in all_rows:
                event_id = row.get("id")
                if not event_id or event_id in seen:
                    continue
                seen.add(event_id)

                comp = self._row_to_competition(row)
                if comp:
                    competitions.append(comp)

            # Enrich with coordinates from detail pages (one per venue)
            venue_coords: dict[str, tuple[float, float] | None] = {}
            venue_to_comps: dict[str, list[ExtractedEvent]] = {}
            for c in competitions:
                if c.latitude is None:
                    venue_to_comps.setdefault(c.venue_name, []).append(c)

            to_fetch = [comps[0] for comps in venue_to_comps.values()]

            if to_fetch:
                logger.info(
                    "Horse Monkey: enriching %d venues (%d events) with detail pages",
                    len(to_fetch), sum(len(v) for v in venue_to_comps.values()),
                )
                sem = asyncio.Semaphore(5)

                async def _fetch_venue_coords(comp):
                    async with sem:
                        try:
                            await self._enrich_from_detail(client, comp)
                            if comp.latitude is not None:
                                venue_coords[comp.venue_name] = (comp.latitude, comp.longitude)
                            else:
                                venue_coords[comp.venue_name] = None
                        except Exception as e:
                            logger.debug("Horse Monkey: detail enrich failed for %s: %s", comp.url, e)
                            venue_coords[comp.venue_name] = None

                await asyncio.gather(*[_fetch_venue_coords(c) for c in to_fetch])

                for venue, comps in venue_to_comps.items():
                    coords = venue_coords.get(venue)
                    if coords:
                        for c in comps:
                            c.latitude, c.longitude = coords

                enriched = sum(1 for c in competitions if c.latitude is not None)
                logger.info("Horse Monkey: %d/%d events have coordinates", enriched, len(competitions))

        self._log_result("Horse Monkey", len(competitions))
        return competitions

    async def _fetch_all_events(self, client, today):
        all_rows: list[dict] = []
        page = 1

        while True:
            payload = {
                "params": {
                    "filter": [
                        {"field": "order_by", "value": "start_asc", "type": "dropdown"},
                        {"field": "events.event_type_id", "value": [COMPETITION_TYPE_ID], "type": "multiselect"},
                        {"field": "events.start", "value": today.isoformat(), "type": "date"},
                    ],
                    "currentPage": page,
                    "perPage": PER_PAGE,
                    "sortBy": "start",
                    "sortDesc": False,
                }
            }

            data = await self._post_json(client, SEARCH_URL, json=payload)
            rows = data.get("rows", [])
            total = data.get("totalRows", 0)
            all_rows.extend(rows)

            logger.debug("Horse Monkey: page %d — %d rows (total %d)", page, len(rows), total)

            if len(all_rows) >= total or not rows:
                break
            page += 1
            await asyncio.sleep(0.2)

        return all_rows

    def _row_to_competition(self, row):
        name = (row.get("name") or "").strip()
        start = row.get("start", "")
        end = row.get("end", "")

        if not name or not start:
            return None

        date_start = self._parse_date(start)
        date_end = self._parse_date(end)
        if not date_start:
            return None

        venue_name = (row.get("venue_name") or "").strip() or "TBC"
        disciplines = (row.get("disciplines") or "").strip()
        public_url = row.get("publicUrl", "")

        text = f"{name} {disciplines}"
        discipline = infer_discipline(text) or disciplines or None
        has_pony = detect_pony_classes(text)

        return self._build_event(
            name=name,
            date_start=date_start,
            date_end=date_end if date_end != date_start else None,
            venue_name=venue_name,
            discipline=discipline,
            has_pony_classes=has_pony,
            classes=[],
            url=public_url or f"https://horsemonkey.com/uk/equestrian_event/{row.get('id')}",
        )

    _LATLONG_RE = re.compile(r'"latitude":"(-?[\d.]+)","longitude":"(-?[\d.]+)"')

    async def _enrich_from_detail(self, client, comp):
        if not comp.url:
            return
        resp = await client.get(
            comp.url,
            headers={"X-Requested-With": "", "Accept": "text/html"},
        )
        resp.raise_for_status()

        m = self._LATLONG_RE.search(resp.text)
        if m:
            try:
                comp.latitude = float(m.group(1))
                comp.longitude = float(m.group(2))
            except (ValueError, TypeError):
                pass
