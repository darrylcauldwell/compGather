from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("csio_barcelona")
class CSIOBarcelonaParser(SingleVenueParser):
    """Parser for CSIO Barcelona — Real Club de Polo, Barcelona, Spain.

    CSIO5* Nations Cup Final and Longines FEI Jumping Nations Cup Final.
    Held at the prestigious Real Club de Polo de Barcelona.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Real Club de Polo, Barcelona"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.csiobarcelona.com/en/"

    SHOW_NAME = "CSIO Barcelona 2026"
    DATE_START = "2026-10-01"
    DATE_END = "2026-10-04"

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
                latitude=41.3867,
                longitude=2.1270,
                url=url,
            )
        ]
        self._log_result("CSIO Barcelona", len(events))
        return events
