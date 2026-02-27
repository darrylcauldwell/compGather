from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("live_oak")
class LiveOakParser(SingleVenueParser):
    """Parser for Live Oak International — Live Oak Stud, Ocala, FL.

    CSI4* show jumping plus CAI combined driving. The only US event
    combining international jumping and driving. 35th edition in 2026.
    25,000+ spectators.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Live Oak Stud, Ocala"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.liveoakinternational.com/"

    SHOW_NAME = "Live Oak International 2026"
    DATE_START = "2026-03-12"
    DATE_END = "2026-03-15"

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
                discipline=None,  # Multi-discipline: SJ + driving
                event_type="show",
                latitude=29.2017,
                longitude=-82.2400,
                url=url,
            )
        ]
        self._log_result("Live Oak International", len(events))
        return events
