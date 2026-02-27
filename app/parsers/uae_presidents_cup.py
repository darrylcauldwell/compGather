from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("uae_presidents_cup")
class UAEPresidentsCupParser(SingleVenueParser):
    """Parser for CSI5* UAE President's Cup — Abu Dhabi Equestrian Club, UAE.

    Prestigious CSI5*/2*/YH show jumping event with record prize money.
    Held at Abu Dhabi Equestrian Club in the Al Mushrif area.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Abu Dhabi Equestrian Club"
    VENUE_POSTCODE = None
    BASE_URL = "https://uaeerf.ae/en/Content/Jumping/Calendar"

    SHOW_NAME = "CSI5* UAE President's Cup 2026"
    DATE_START = "2026-01-07"
    DATE_END = "2026-01-11"

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
                event_type="competition",
                latitude=24.4550,
                longitude=54.3800,
                url=url,
            )
        ]
        self._log_result("UAE President's Cup", len(events))
        return events
