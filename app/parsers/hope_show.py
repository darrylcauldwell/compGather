from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("hope_show")
class HopeShowParser(SingleVenueParser):
    """Parser for the Hope Show — Marsh Farm, Hope, Derbyshire.

    Traditional agricultural show held on August Bank Holiday Monday.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Hope Showground"
    VENUE_POSTCODE = "S33 8RZ"
    BASE_URL = "https://www.hopeshow.co.uk"

    SHOW_NAME = "Hope Show 2026"
    DATE_START = "2026-08-31"
    DATE_END = "2026-08-31"

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
                discipline=None,
                event_type="show",
                url=url,
            )
        ]
        self._log_result("Hope Show", len(events))
        return events
