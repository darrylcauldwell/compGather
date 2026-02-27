from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("ocala")
class OcalaParser(SingleVenueParser):
    """Parser for Ocala Winter Spectacular — World Equestrian Center, Ocala, FL, USA.

    12-week premier show jumping and hunter circuit running Dec-Mar each year.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "World Equestrian Center, Ocala"
    VENUE_POSTCODE = None
    BASE_URL = "https://worldequestriancenter.com/ocala-fl/equestrian/shows/winter-spectacular/"

    SHOW_NAME = "Ocala Winter Spectacular 2026"
    DATE_START = "2025-12-31"
    DATE_END = "2026-03-22"

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
                latitude=29.1872,
                longitude=-82.1401,
                url=url,
            )
        ]
        self._log_result("Ocala", len(events))
        return events
