from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("chio_rotterdam")
class CHIORotterdamParser(SingleVenueParser):
    """Parser for CHIO Rotterdam — Kralingse Bos, Rotterdam, Netherlands.

    CSIO5* Nations Cup (Longines League of Nations) and CDI dressage event.
    Held annually in Kralingse Bos park (77th edition in 2026).
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Kralingse Bos, Rotterdam"
    VENUE_POSTCODE = None
    BASE_URL = "https://chio.nl/en"

    SHOW_NAME = "CHIO Rotterdam 2026"
    DATE_START = "2026-06-18"
    DATE_END = "2026-06-21"

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
                latitude=51.9265,
                longitude=4.4900,
                url=url,
            )
        ]
        self._log_result("CHIO Rotterdam", len(events))
        return events
