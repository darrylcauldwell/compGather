from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("jumping_verona")
class JumpingVeronaParser(SingleVenueParser):
    """Parser for Jumping Verona — Fieracavalli, Veronafiere, Italy.

    CSI5*-W World Cup qualifier held inside Fieracavalli, Italy's largest
    equestrian fair. Combines top-level show jumping with a massive horse expo.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Veronafiere"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.fieracavalli.it/en/"

    SHOW_NAME = "Jumping Verona — Fieracavalli 2026"
    DATE_START = "2026-11-05"
    DATE_END = "2026-11-08"

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
                latitude=45.4289,
                longitude=10.9628,
                url=url,
            )
        ]
        self._log_result("Jumping Verona", len(events))
        return events
