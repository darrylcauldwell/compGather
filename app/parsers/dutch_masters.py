from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("dutch_masters")
class DutchMastersParser(SingleVenueParser):
    """Parser for The Dutch Masters — Indoor Brabant, Den Bosch, Netherlands.

    CSI5*-W / CDI-W and part of the Rolex Grand Slam of Show Jumping
    (alongside CHI Geneva, Spruce Meadows Masters, and CHIO Aachen).
    Final World Cup qualifier before the annual World Cup Finals.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Brabanthallen, Den Bosch"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.thedutchmasters.com/en/"

    SHOW_NAME = "The Dutch Masters 2026"
    DATE_START = "2026-03-12"
    DATE_END = "2026-03-15"

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
                latitude=51.6978,
                longitude=5.3037,
                url=url,
            )
        ]
        self._log_result("The Dutch Masters", len(events))
        return events
