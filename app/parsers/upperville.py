from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("upperville")
class UppervilleParser(SingleVenueParser):
    """Parser for Upperville Colt & Horse Show — Upperville, VA.

    The oldest horse show in America, established 1853. 173rd anniversary
    in 2026. Set in Virginia hunt country. USEF Premier.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Grafton & Salem Showgrounds, Upperville"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.upperville.com/"

    SHOW_NAME = "Upperville Colt & Horse Show 2026"
    DATE_START = "2026-06-01"
    DATE_END = "2026-06-07"

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
                discipline="Show Jumping",
                event_type="show",
                latitude=38.9693,
                longitude=-77.8786,
                url=url,
            )
        ]
        self._log_result("Upperville", len(events))
        return events
