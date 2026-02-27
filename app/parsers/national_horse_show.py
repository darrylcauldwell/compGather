from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("national_horse_show")
class NationalHorseShowParser(SingleVenueParser):
    """Parser for National Horse Show — Tryon International EC, Mill Spring, NC.

    CSI5*, USEF Premier. America's oldest championship horse show, established
    1883. 143rd edition in 2026. Includes the prestigious ASPCA Maclay
    National Championship equitation finals.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Tryon International Equestrian Center"
    VENUE_POSTCODE = None
    BASE_URL = "https://nhs.org/"

    SHOW_NAME = "National Horse Show 2026"
    DATE_START = "2026-10-21"
    DATE_END = "2026-11-01"

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
                latitude=35.3261,
                longitude=-82.1532,
                url=url,
            )
        ]
        self._log_result("National Horse Show", len(events))
        return events
