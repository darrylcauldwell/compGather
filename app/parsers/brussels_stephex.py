from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("brussels_stephex")
class BrusselsStephexParser(SingleVenueParser):
    """Parser for Brussels Stephex Masters — Stephex Stables, Brussels, Belgium.

    CSIO5* Longines Rolex Series event. One of Europe's premier outdoor
    show jumping events, held at Stephex Stables south of Brussels.
    Part of the Rolex Grand Prix series circuit.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Stephex Stables, Brussels"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.stephexmasters.com/"

    SHOW_NAME = "Brussels Stephex Masters 2026"
    DATE_START = "2026-08-27"
    DATE_END = "2026-08-30"

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
                latitude=50.8167,
                longitude=4.2833,
                url=url,
            )
        ]
        self._log_result("Brussels Stephex", len(events))
        return events
