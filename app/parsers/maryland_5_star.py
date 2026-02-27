from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("maryland_5_star")
class Maryland5StarParser(SingleVenueParser):
    """Parser for Maryland 5 Star at Fair Hill — CCI5*-L eventing, Elkton, MD, USA.

    One of only seven CCI5* events worldwide.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Fair Hill"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.maryland5star.us"

    SHOW_NAME = "Maryland 5 Star at Fair Hill 2026"
    DATE_START = "2026-10-15"
    DATE_END = "2026-10-18"

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
                discipline="Eventing",
                event_type="show",
                latitude=39.7048,
                longitude=-75.8399,
                url=url,
            )
        ]
        self._log_result("Maryland 5 Star", len(events))
        return events
