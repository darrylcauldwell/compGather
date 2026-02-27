from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("kentucky_three_day")
class KentuckyThreeDayParser(SingleVenueParser):
    """Parser for Defender Kentucky Three-Day Event — Kentucky Horse Park, Lexington, KY.

    CCI5*-L — one of only six 5-star eventing competitions in the world
    (alongside Badminton, Burghley, Luhmuhlen, Pau, and Maryland 5 Star).
    Also hosts the Kentucky International CSI5* show jumping concurrently.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Kentucky Horse Park, Lexington"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.kentuckythreedayevent.com/"

    SHOW_NAME = "Kentucky Three-Day Event CCI5*-L 2026"
    DATE_START = "2026-04-23"
    DATE_END = "2026-04-26"

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
                discipline="Eventing",
                event_type="show",
                latitude=38.1500,
                longitude=-84.5206,
                url=url,
            )
        ]
        self._log_result("Kentucky Three-Day", len(events))
        return events
