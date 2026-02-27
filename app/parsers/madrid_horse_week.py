from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("madrid_horse_week")
class MadridHorseWeekParser(SingleVenueParser):
    """Parser for Madrid Horse Week — IFEMA, Madrid, Spain.

    CSI5*-W World Cup qualifier. Spain's premier indoor equestrian event
    held at the IFEMA Feria de Madrid convention centre.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "IFEMA, Madrid"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.madridhorseweek.com/en/"

    SHOW_NAME = "Madrid Horse Week 2026"
    DATE_START = "2026-11-26"
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
                latitude=40.4668,
                longitude=-3.6171,
                url=url,
            )
        ]
        self._log_result("Madrid Horse Week", len(events))
        return events
