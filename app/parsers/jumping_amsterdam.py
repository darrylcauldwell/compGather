from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("jumping_amsterdam")
class JumpingAmsterdamParser(SingleVenueParser):
    """Parser for Jumping Amsterdam — RAI Amsterdam, Netherlands.

    CSI5*-W / CDI-W FEI World Cup qualifier. One of the most prestigious
    indoor equestrian events in the world (65th edition in 2026).
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "RAI Amsterdam"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.jumpingamsterdam.nl/en/"

    SHOW_NAME = "Jumping Amsterdam 2026"
    DATE_START = "2026-01-22"
    DATE_END = "2026-01-25"

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
                latitude=52.3414,
                longitude=4.8880,
                url=url,
            )
        ]
        self._log_result("Jumping Amsterdam", len(events))
        return events
