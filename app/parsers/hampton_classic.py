from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("hampton_classic")
class HamptonClassicParser(SingleVenueParser):
    """Parser for Hampton Classic Horse Show — Bridgehampton, NY.

    CSI4*, one of the largest and most prestigious outdoor horse shows in the US.
    Major social event in the Hamptons over Labor Day weekend.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Hampton Classic Showgrounds, Bridgehampton"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.hamptonclassic.com/"

    SHOW_NAME = "Hampton Classic Horse Show 2026"
    DATE_START = "2026-08-23"
    DATE_END = "2026-08-30"

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
                latitude=40.9227,
                longitude=-72.3133,
                url=url,
            )
        ]
        self._log_result("Hampton Classic", len(events))
        return events
