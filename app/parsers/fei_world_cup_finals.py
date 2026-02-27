from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("fei_world_cup_finals")
class FEIWorldCupFinalsParser(SingleVenueParser):
    """Parser for FEI World Cup Finals 2026 — Dickies Arena, Fort Worth, TX.

    The annual individual world championship for show jumping and dressage.
    Rotates globally; Fort Worth hosts the 2026 edition.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Dickies Arena, Fort Worth"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.fortworth2026.com/"

    SHOW_NAME = "FEI World Cup Finals 2026"
    DATE_START = "2026-04-08"
    DATE_END = "2026-04-12"

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
                discipline=None,  # Multi-discipline: SJ + dressage
                event_type="show",
                latitude=32.7409,
                longitude=-97.3689,
                url=url,
            )
        ]
        self._log_result("FEI World Cup Finals", len(events))
        return events
