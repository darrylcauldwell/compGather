from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("dinard")
class DinardParser(SingleVenueParser):
    """Parser for Jumping International de Dinard — Hippodrome, Dinard, France.

    CSI5* Longines Rolex Series event. Prestigious outdoor show jumping
    at the Hippodrome de la Barre in Dinard, Brittany.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Hippodrome de Dinard"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.jumpingdinard.com/"

    SHOW_NAME = "Jumping International de Dinard CSI5* 2026"
    DATE_START = "2026-07-30"
    DATE_END = "2026-08-02"

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
                latitude=48.6311,
                longitude=-2.0658,
                url=url,
            )
        ]
        self._log_result("Dinard", len(events))
        return events
