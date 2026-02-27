from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("carolina_international")
class CarolinaInternationalParser(SingleVenueParser):
    """Parser for Carolina International CCI — Carolina Horse Park, Raeford, NC.

    CCI4*-S, one of the premier spring eventing competitions in the US.
    Held at the purpose-built Carolina Horse Park.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Carolina Horse Park, Raeford"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.carolinahorsepark.com/"

    SHOW_NAME = "Carolina International CCI4*-S 2026"
    DATE_START = "2026-03-19"
    DATE_END = "2026-03-22"

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
                discipline="Eventing",
                event_type="competition",
                latitude=35.0400,
                longitude=-79.2700,
                url=url,
            )
        ]
        self._log_result("Carolina International", len(events))
        return events
