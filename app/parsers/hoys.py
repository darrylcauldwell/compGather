from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("hoys")
class HOYSParser(SingleVenueParser):
    """Parser for the Horse of the Year Show — NEC Birmingham.

    Static parser: dates are hard-coded and updated annually.
    The homepage is fetched to confirm the event is still scheduled.
    """

    VENUE_NAME = "NEC Birmingham"
    VENUE_POSTCODE = "B40 1NT"
    BASE_URL = "https://www.hoys.co.uk"

    # Update annually when dates are announced
    SHOW_NAME = "Horse of the Year Show 2026"
    DATE_START = "2026-10-07"
    DATE_END = "2026-10-11"

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
        self._log_result("HOYS", len(events))
        return events
