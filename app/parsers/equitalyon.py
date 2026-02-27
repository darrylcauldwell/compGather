from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("equitalyon")
class EquitaLyonParser(SingleVenueParser):
    """Parser for Equita Lyon — Eurexpo Lyon, France.

    Major equestrian trade fair and CSI5*-W FEI World Cup qualifier.
    One of only two events worldwide hosting four FEI World Cup disciplines.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Eurexpo Lyon"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.equitalyon.com/en"

    SHOW_NAME = "Equita Lyon 2026"
    DATE_START = "2026-10-28"
    DATE_END = "2026-11-01"

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
                latitude=45.7380,
                longitude=4.9401,
                url=url,
            )
        ]
        self._log_result("Equita Lyon", len(events))
        return events
