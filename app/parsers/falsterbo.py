from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("falsterbo")
class FalsterboParser(SingleVenueParser):
    """Parser for Falsterbo Horse Show — Falsterbo, Sweden.

    CSIO5* Nations Cup, one of the oldest and most prestigious outdoor
    equestrian events in Scandinavia. Also features dressage (CDIO5*)
    and eventing (CCI4*-S). Held annually since 1920.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Falsterbo Horse Show"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.falsterbohorseshow.com/en/"

    SHOW_NAME = "Falsterbo Horse Show 2026"
    DATE_START = "2026-07-04"
    DATE_END = "2026-07-12"

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
                discipline=None,  # Multi-discipline: SJ, dressage, eventing
                event_type="show",
                latitude=55.3850,
                longitude=12.8233,
                url=url,
            )
        ]
        self._log_result("Falsterbo", len(events))
        return events
