from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("your_horse_live")
class YourHorseLiveParser(SingleVenueParser):
    """Parser for Your Horse Live — Stoneleigh Park.

    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Stoneleigh Park"
    VENUE_POSTCODE = "CV8 2LZ"
    BASE_URL = "https://www.yourhorse.co.uk/yourhorselive/"

    SHOW_NAME = "Your Horse Live 2026"
    DATE_START = "2026-11-06"
    DATE_END = "2026-11-08"

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
        self._log_result("Your Horse Live", len(events))
        return events
