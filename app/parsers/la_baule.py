from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("la_baule")
class LaBauleParser(SingleVenueParser):
    """Parser for La Baule — Stade Francois Andre, La Baule, France.

    CSIO5* Longines Global Champions Tour / Rolex Series event.
    One of France's most prestigious outdoor show jumping events,
    held at the beachfront Stade Francois Andre in La Baule-Escoublac.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Stade Francois Andre, La Baule"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.jumpinglabaule.com/en/"

    SHOW_NAME = "Jumping La Baule CSIO5* 2026"
    DATE_START = "2026-06-11"
    DATE_END = "2026-06-14"

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
                latitude=47.2806,
                longitude=-2.3928,
                url=url,
            )
        ]
        self._log_result("La Baule", len(events))
        return events
