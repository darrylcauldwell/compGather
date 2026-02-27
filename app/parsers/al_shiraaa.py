from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("al_shiraaa")
class AlShiraaaParser(SingleVenueParser):
    """Parser for Al Shira'aa International Horse Show — Al Forsan, Abu Dhabi, UAE.

    CSI4*-W FEI World Cup qualifier held at Al Forsan International Sports Resort.
    Features 350+ horses and 150+ riders.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Al Forsan International Sports Resort"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.alshiraatour.com/abu-dhabi"

    SHOW_NAME = "Al Shira'aa International Horse Show 2026"
    DATE_START = "2026-01-20"
    DATE_END = "2026-01-25"

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
                event_type="competition",
                latitude=24.4190,
                longitude=54.6550,
                url=url,
            )
        ]
        self._log_result("Al Shira'aa International", len(events))
        return events
