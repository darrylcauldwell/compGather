from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("sunshine_tour")
class SunshineTourParser(SingleVenueParser):
    """Parser for the Andalucia Sunshine Tour — Montenmedio, Vejer de la Frontera, Spain.

    Major international show jumping circuit running Feb-Mar each year.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Montenmedio"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.sunshinetour.net"

    SHOW_NAME = "Andalucia Sunshine Tour 2026"
    DATE_START = "2026-02-02"
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
                latitude=36.2519,
                longitude=-5.8686,
                url=url,
            )
        ]
        self._log_result("Sunshine Tour", len(events))
        return events
