from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("gothenburg")
class GothenburgParser(SingleVenueParser):
    """Parser for Gothenburg Horse Show — Scandinavium, Gothenburg, Sweden.

    Major FEI World Cup qualifier for both jumping and dressage.
    Held alongside the EuroHorse fair.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Scandinavium, Gothenburg"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.gothenburghorseshow.com/en/"

    SHOW_NAME = "Gothenburg Horse Show 2026"
    DATE_START = "2026-02-18"
    DATE_END = "2026-02-22"

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
                latitude=57.6928,
                longitude=11.9860,
                url=url,
            )
        ]
        self._log_result("Gothenburg Horse Show", len(events))
        return events
