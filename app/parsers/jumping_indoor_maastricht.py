from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("jumping_indoor_maastricht")
class JumpingIndoorMaastrichtParser(SingleVenueParser):
    """Parser for Jumping Indoor Maastricht — MECC Maastricht, Netherlands.

    CSI5* show jumping event with FEI Driving World Cup qualifier.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "MECC Maastricht"
    VENUE_POSTCODE = None
    BASE_URL = "https://jumpingindoormaastricht.com/en/home-en/"

    SHOW_NAME = "Jumping Indoor Maastricht 2026"
    DATE_START = "2026-11-05"
    DATE_END = "2026-11-08"

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
                latitude=50.8397,
                longitude=5.7104,
                url=url,
            )
        ]
        self._log_result("Jumping Indoor Maastricht", len(events))
        return events
