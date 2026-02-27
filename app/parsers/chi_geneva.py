from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("chi_geneva")
class CHIGenevaParser(SingleVenueParser):
    """Parser for CHI Geneva — Palexpo, Geneva, Switzerland.

    Part of the Rolex Grand Slam of Show Jumping (alongside CHIO Aachen,
    Spruce Meadows Masters, and The Dutch Masters). One of the world's most
    prestigious indoor shows. CSI5*-W / CDI-W.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Palexpo, Geneva"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.chi-geneve.ch/en/"

    SHOW_NAME = "CHI Geneva 2026"
    DATE_START = "2026-12-10"
    DATE_END = "2026-12-13"

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
                latitude=46.2333,
                longitude=6.1167,
                url=url,
            )
        ]
        self._log_result("CHI Geneva", len(events))
        return events
