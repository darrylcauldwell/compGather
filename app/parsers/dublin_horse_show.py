from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("dublin_horse_show")
class DublinHorseShowParser(SingleVenueParser):
    """Parser for Dublin Horse Show — RDS, Dublin, Ireland.

    CSIO5* Nations Cup and one of the longest-running horse shows in the world
    (since 1868). Also features international dressage and showing classes.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "RDS, Dublin"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.dublinhorseshow.com/"

    SHOW_NAME = "Dublin Horse Show 2026"
    DATE_START = "2026-08-05"
    DATE_END = "2026-08-09"

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
                latitude=53.3254,
                longitude=-6.2312,
                url=url,
            )
        ]
        self._log_result("Dublin Horse Show", len(events))
        return events
