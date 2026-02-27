from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("great_meadow")
class GreatMeadowParser(SingleVenueParser):
    """Parser for MARS Great Meadow International — The Plains, VA.

    CCI4*-S with the only FEI Eventing Nations Cup leg in North America.
    Created by Olympian David O'Connor. Set in Virginia hunt country.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Great Meadow, The Plains"
    VENUE_POSTCODE = None
    BASE_URL = "https://greatmeadow.org/"

    SHOW_NAME = "MARS Great Meadow International 2026"
    DATE_START = "2026-07-03"
    DATE_END = "2026-07-05"

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
                event_type="show",
                latitude=38.8620,
                longitude=-77.7600,
                url=url,
            )
        ]
        self._log_result("Great Meadow", len(events))
        return events
