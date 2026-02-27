from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("cavaliada")
class CAVALIADAParser(SingleVenueParser):
    """Parser for CAVALIADA — Tauron Arena, Krakow, Poland.

    CSI2*-4* indoor show jumping tour. CAVALIADA is Poland's biggest indoor
    equestrian event, rotating between Krakow, Warsaw, and Poznan.
    This parser covers the Krakow edition at Tauron Arena.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Tauron Arena, Krakow"
    VENUE_POSTCODE = None
    BASE_URL = "https://cavaliada.pl/en/"

    SHOW_NAME = "CAVALIADA Krakow 2026"
    DATE_START = "2026-02-26"
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
                discipline="Show Jumping",
                event_type="show",
                latitude=50.0645,
                longitude=20.0100,
                url=url,
            )
        ]
        self._log_result("CAVALIADA", len(events))
        return events
