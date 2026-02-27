from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("pennsylvania_national")
class PennsylvaniaNationalParser(SingleVenueParser):
    """Parser for Pennsylvania National Horse Show — Harrisburg, PA.

    80th edition in 2026. Major indoor fall championship event at the
    Pennsylvania Farm Show Complex. Features the $100,000 Grand Prix
    de Penn National.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Pennsylvania Farm Show Complex, Harrisburg"
    VENUE_POSTCODE = None
    BASE_URL = "https://panational.org/"

    SHOW_NAME = "Pennsylvania National Horse Show 2026"
    DATE_START = "2026-10-08"
    DATE_END = "2026-10-18"

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
                latitude=40.2765,
                longitude=-76.8813,
                url=url,
            )
        ]
        self._log_result("Pennsylvania National", len(events))
        return events
