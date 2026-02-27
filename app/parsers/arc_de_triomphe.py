from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("arc_de_triomphe")
class ArcDeTriompheParser(SingleVenueParser):
    """Parser for Prix de l'Arc de Triomphe — ParisLongchamp, Paris, France.

    Europe's richest flat horse race, held first weekend of October annually.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "ParisLongchamp"
    VENUE_POSTCODE = None
    BASE_URL = "https://billetterie.france-galop.com/en/event/qatar-prix-de-larc-de-triomphe/"

    SHOW_NAME = "Prix de l'Arc de Triomphe 2026"
    DATE_START = "2026-10-03"
    DATE_END = "2026-10-04"

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
                discipline="Flat Racing",
                event_type="show",
                latitude=48.8575,
                longitude=2.2310,
                url=url,
            )
        ]
        self._log_result("Arc de Triomphe", len(events))
        return events
