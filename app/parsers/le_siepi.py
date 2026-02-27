from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("le_siepi")
class LeSiepiParser(SingleVenueParser):
    """Parser for Adriatic Tour — Circolo Ippico Le Siepi, Milano Marittima, Italy.

    CSI2*/1*/YH show jumping event in the pine forest of Milano Marittima
    (Cervia). One of Italy's most established equestrian centres since 1974.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Circolo Ippico Le Siepi"
    VENUE_POSTCODE = None
    BASE_URL = "https://lesiepicervia.it/"

    SHOW_NAME = "Adriatic Tour 2026"
    DATE_START = "2026-07-30"
    DATE_END = "2026-08-02"

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
                latitude=44.2680,
                longitude=12.3550,
                url=url,
            )
        ]
        self._log_result("Adriatic Tour (Le Siepi)", len(events))
        return events
