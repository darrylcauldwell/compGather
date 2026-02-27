from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("devon_horse_show")
class DevonHorseShowParser(SingleVenueParser):
    """Parser for Devon Horse Show — Devon, PA.

    America's oldest and most prestigious outdoor horse show, established 1896.
    130th edition in 2026. CSI4*, USEF Premier hunters/jumpers/equitation.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Devon Horse Show Grounds"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.devonhorseshow.net/"

    SHOW_NAME = "Devon Horse Show 2026"
    DATE_START = "2026-05-21"
    DATE_END = "2026-06-01"

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
                latitude=40.0474,
                longitude=-75.4198,
                url=url,
            )
        ]
        self._log_result("Devon Horse Show", len(events))
        return events
