from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("national_equine_show")
class NationalEquineShowParser(SingleVenueParser):
    """Parser for the National Equine Show — NEC Birmingham.

    UK's premier spring equestrian shopping and lifestyle event.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "NEC Birmingham"
    VENUE_POSTCODE = "B40 1NT"
    BASE_URL = "https://nationalequineshow.com"

    SHOW_NAME = "National Equine Show 2026"
    DATE_START = "2026-02-28"
    DATE_END = "2026-03-01"

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
                discipline=None,
                event_type="show",
                url=url,
            )
        ]
        self._log_result("National Equine Show", len(events))
        return events
