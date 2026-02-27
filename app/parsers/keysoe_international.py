from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("keysoe_international")
class KeysoeInternationalParser(SingleVenueParser):
    """Parser for Keysoe International — The College EC, Bedfordshire, UK.

    CSI2* level international show jumping event held in partnership
    with British Showjumping.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "The College Equestrian Centre, Keysoe"
    VENUE_POSTCODE = "MK44 2JP"
    BASE_URL = "https://www.keysoe.com/"

    SHOW_NAME = "Keysoe International CSI2* 2026"
    DATE_START = "2026-07-02"
    DATE_END = "2026-07-04"

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
                latitude=52.2540,
                longitude=-0.4238,
                url=url,
            )
        ]
        self._log_result("Keysoe International", len(events))
        return events
