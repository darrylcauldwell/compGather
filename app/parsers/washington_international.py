from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("washington_international")
class WashingtonInternationalParser(SingleVenueParser):
    """Parser for Washington International Horse Show — Upper Marlboro, MD.

    CSI4*-W World Cup qualifier. DC's premier equestrian event, 68th annual
    in 2026. Features Olympic-caliber athletes and the prestigious
    WIHS Equitation Finals.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Show Place Arena, Upper Marlboro"
    VENUE_POSTCODE = None
    BASE_URL = "https://wihs.org/"

    SHOW_NAME = "Washington International Horse Show 2026"
    DATE_START = "2026-10-19"
    DATE_END = "2026-10-25"

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
                latitude=38.8163,
                longitude=-76.7497,
                url=url,
            )
        ]
        self._log_result("Washington International", len(events))
        return events
