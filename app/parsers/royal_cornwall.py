from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("royal_cornwall")
class RoyalCornwallParser(SingleVenueParser):
    """Parser for the Royal Cornwall Show — Royal Cornwall Showground, Wadebridge.

    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Royal Cornwall Showground"
    VENUE_POSTCODE = "PL27 7JE"
    BASE_URL = "https://www.royalcornwallshow.org"

    SHOW_NAME = "Royal Cornwall Show 2026"
    DATE_START = "2026-06-04"
    DATE_END = "2026-06-06"

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
        self._log_result("Royal Cornwall Show", len(events))
        return events
