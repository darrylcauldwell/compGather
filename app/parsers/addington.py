from __future__ import annotations

import html
import logging
from datetime import date

import httpx

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import (
    detect_pony_classes,
    infer_discipline,
    is_competition_event,
    is_future_event,
)
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

API_URL = "https://addington.co.uk/wp-json/tribe/events/v1/events"
VENUE_NAME = "Addington"
VENUE_POSTCODE = "MK18 2JR"
PER_PAGE = 50

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


@register_parser("addington")
class AddingtonParser(BaseParser):
    """Parser for addington.co.uk — Tribe Events Calendar REST API.

    All events are at Addington Equestrian Centre (MK18 2JR).
    The API returns structured JSON with full event data.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=30.0, headers=HEADERS
        ) as client:
            all_events: list[dict] = []
            today = date.today().isoformat()

            # Fetch first page
            params = {
                "per_page": PER_PAGE,
                "start_date": today,
            }
            resp = await client.get(API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

            events = data.get("events", [])
            all_events.extend(events)
            total = data.get("total", 0)
            total_pages = data.get("total_pages", 1)
            logger.info("Addington: %d total events, %d pages", total, total_pages)

            # Paginate if needed
            for page in range(2, total_pages + 1):
                next_url = data.get("next_rest_url")
                if not next_url:
                    break
                resp = await client.get(next_url)
                resp.raise_for_status()
                data = resp.json()
                all_events.extend(data.get("events", []))

            # Convert to competitions
            competitions: list[ExtractedCompetition] = []
            for event in all_events:
                comp = self._event_to_competition(event)
                if comp:
                    competitions.append(comp)

        logger.info("Addington: extracted %d competitions", len(competitions))
        return competitions

    def _event_to_competition(self, event: dict) -> ExtractedCompetition | None:
        """Convert a Tribe Events API event to an ExtractedCompetition."""
        title = html.unescape(event.get("title", "")).strip()
        start_date = event.get("start_date", "")
        end_date = event.get("end_date", "")
        event_url = event.get("url", "")

        if not title or not start_date:
            return None

        # Extract just the date portion (API returns "2026-02-20 00:00:00")
        date_start = start_date[:10]
        date_end = end_date[:10] if end_date else None

        if not is_future_event(date_start, date_end):
            return None

        # Filter non-competition events
        if not is_competition_event(title):
            return None

        # Infer discipline from title
        discipline = infer_discipline(title)
        has_pony = detect_pony_classes(title)

        return ExtractedCompetition(
            name=title,
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name=VENUE_NAME,
            venue_postcode=VENUE_POSTCODE,
            discipline=discipline,
            has_pony_classes=has_pony,
            classes=[],
            url=event_url,
        )
