from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("luhmuhlen")
class LuhmuhlenParser(SingleVenueParser):
    """Parser for Luhmuhlen Horse Trials — CCI5*-L eventing, Salzhausen, Germany.

    One of only seven CCI5* events worldwide.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Luhmuhlen"
    VENUE_POSTCODE = None
    BASE_URL = "https://tgl.luhmuehlen.de/en"

    SHOW_NAME = "Luhmuhlen Horse Trials 2026"
    DATE_START = "2026-06-18"
    DATE_END = "2026-06-21"

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
                latitude=53.2567,
                longitude=10.0333,
                url=url,
            )
        ]
        self._log_result("Luhmuhlen", len(events))
        return events
