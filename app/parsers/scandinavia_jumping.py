from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("scandinavia_jumping")
class ScandinaviaJumpingParser(SingleVenueParser):
    """Parser for Scandinavia Jumping Tour — Odense Congress Center, Denmark.

    Show jumping and pony competition held during Danish winter school break.
    Free admission. Features pony and senior classes.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Odense Congress Center"
    VENUE_POSTCODE = None
    BASE_URL = "https://occ.dk/en/nyheder/scandinavia-jumping-tour-2026/"

    SHOW_NAME = "Scandinavia Jumping Tour 2026"
    DATE_START = "2026-02-06"
    DATE_END = "2026-02-14"

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
                latitude=55.3960,
                longitude=10.3880,
                url=url,
            )
        ]
        self._log_result("Scandinavia Jumping Tour", len(events))
        return events
