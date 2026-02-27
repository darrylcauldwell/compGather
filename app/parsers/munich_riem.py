from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("munich_riem")
class MunichRiemParser(SingleVenueParser):
    """Parser for Pferd International München — Olympia-Reitanlage München-Riem, Germany.

    CDI5*/CSI3* event at the historic 1972 Olympic equestrian facility.
    Largest equestrian event in southern Germany (85,000+ visitors).
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Olympia-Reitanlage München-Riem"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.pferdinternational.de/"

    SHOW_NAME = "Pferd International München 2026"
    DATE_START = "2026-05-14"
    DATE_END = "2026-05-17"

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
                latitude=48.1431,
                longitude=11.6662,
                url=url,
            )
        ]
        self._log_result("Pferd International München", len(events))
        return events
