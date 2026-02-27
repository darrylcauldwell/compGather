from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("dubai_sj_championship")
class DubaiSJChampionshipParser(SingleVenueParser):
    """Parser for Dubai Show Jumping Championship CSI5* — Emirates EC, Dubai, UAE.

    CSI5* show jumping event held at the Emirates Equestrian Centre,
    the only fully BHS-approved riding centre in the Middle East.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Emirates Equestrian Centre"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.emiratesequestriancentre.com/dubai-show-jumping-championship"

    SHOW_NAME = "Dubai Show Jumping Championship CSI5* 2026"
    DATE_START = "2026-01-15"
    DATE_END = "2026-01-18"

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
                latitude=25.0920,
                longitude=55.3750,
                url=url,
            )
        ]
        self._log_result("Dubai SJ Championship", len(events))
        return events
