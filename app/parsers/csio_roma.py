from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("csio_roma")
class CSIORomaParser(SingleVenueParser):
    """Parser for CSIO Roma — Piazza di Siena, Villa Borghese, Rome, Italy.

    One of the most prestigious outdoor shows in the world, held in the
    stunning Piazza di Siena amphitheatre inside Villa Borghese gardens.
    CSIO5* Nations Cup event, celebrating its centenary in 2026.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Piazza di Siena, Roma"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.piazzadisiena.it/en/"

    SHOW_NAME = "CSIO Roma — Piazza di Siena 2026"
    DATE_START = "2026-05-28"
    DATE_END = "2026-05-31"

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
                latitude=41.9147,
                longitude=12.4842,
                url=url,
            )
        ]
        self._log_result("CSIO Roma", len(events))
        return events
