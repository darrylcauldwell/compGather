from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("spruce_meadows")
class SpruceMeadowsParser(SingleVenueParser):
    """Parser for Spruce Meadows Masters — Calgary, Alberta, Canada.

    World-class international show jumping tournament, part of the Rolex Grand Slam.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Spruce Meadows"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.sprucemeadows.com/masters/"

    SHOW_NAME = "Spruce Meadows Masters 2026"
    DATE_START = "2026-09-09"
    DATE_END = "2026-09-13"

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
                latitude=50.8745,
                longitude=-114.1066,
                url=url,
            )
        ]
        self._log_result("Spruce Meadows", len(events))
        return events
