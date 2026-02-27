from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("stockholm_horse_show")
class StockholmHorseShowParser(SingleVenueParser):
    """Parser for Stockholm International Horse Show — Friends Arena, Stockholm, Sweden.

    CSI4*/CDI5*-W. Scandinavia's premier indoor show held at Friends Arena
    in Solna. World Cup qualifier for both show jumping and dressage.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Friends Arena, Stockholm"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.stockholmhorseshow.com/"

    SHOW_NAME = "Stockholm International Horse Show 2026"
    DATE_START = "2026-11-27"
    DATE_END = "2026-11-29"

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
                latitude=59.3725,
                longitude=18.0000,
                url=url,
            )
        ]
        self._log_result("Stockholm Horse Show", len(events))
        return events
