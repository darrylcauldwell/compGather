from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("trailblazers")
class TrailblazersParser(SingleVenueParser):
    """Parser for SEIB Trailblazers Championships — Addington Manor, Buckinghamshire.

    Annual grassroots championship finals for show jumping, dressage, and combined training.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Addington Manor"
    VENUE_POSTCODE = "MK18 2JR"
    BASE_URL = "https://www.trailblazerschampionships.com"

    SHOW_NAME = "SEIB Trailblazers Championships 2026"
    DATE_START = "2026-07-31"
    DATE_END = "2026-08-03"

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("%s: site unreachable, returning static data", self.SHOW_NAME)

        events = [
            self._build_event(
                name=self.SHOW_NAME,
                date_start=self.DATE_START,
                date_end=self.DATE_END,
                discipline=None,
                event_type="show",
                url=url,
            )
        ]
        self._log_result("Trailblazers", len(events))
        return events
