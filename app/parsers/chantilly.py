from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("chantilly")
class ChantillyParser(SingleVenueParser):
    """Parser for Chantilly Classic — Domaine de Chantilly, France.

    International show jumping at CSI4*/2*/1*/YH level on the Chantilly
    racecourse with the Chateau de Chantilly as backdrop.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Domaine de Chantilly"
    VENUE_POSTCODE = None
    BASE_URL = "https://grandprix-events.com/en/chantilly-classic/"

    SHOW_NAME = "Chantilly Classic 2026"
    DATE_START = "2026-07-10"
    DATE_END = "2026-07-13"

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
                latitude=49.1883,
                longitude=2.4717,
                url=url,
            )
        ]
        self._log_result("Chantilly Classic", len(events))
        return events
