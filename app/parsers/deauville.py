from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("deauville")
class DeauvilleParser(SingleVenueParser):
    """Parser for Deauville — Pole International du Cheval, Deauville, France.

    CSI4* international show jumping at the Pole International du Cheval
    in Deauville, Normandy. Part of the strong French outdoor circuit.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Pole International du Cheval, Deauville"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.pfrancecomplet.com/"

    SHOW_NAME = "Jumping International de Deauville CSI4* 2026"
    DATE_START = "2026-08-13"
    DATE_END = "2026-08-16"

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
                latitude=49.3475,
                longitude=0.0656,
                url=url,
            )
        ]
        self._log_result("Deauville", len(events))
        return events
