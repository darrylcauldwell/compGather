from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("oslo_horse_show")
class OsloHorseShowParser(SingleVenueParser):
    """Parser for Oslo Horse Show — Telenor Arena, Oslo, Norway.

    CSI5*-W World Cup qualifier. Norway's biggest indoor equestrian event,
    held at Telenor Arena in Fornebu. Also features CDI dressage.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Telenor Arena, Oslo"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.oslohorseshow.com/"

    SHOW_NAME = "Oslo Horse Show 2026"
    DATE_START = "2026-10-09"
    DATE_END = "2026-10-11"

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
                latitude=59.9075,
                longitude=10.6317,
                url=url,
            )
        ]
        self._log_result("Oslo Horse Show", len(events))
        return events
