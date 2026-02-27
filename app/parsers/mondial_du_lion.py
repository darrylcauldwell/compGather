from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("mondial_du_lion")
class MondialDuLionParser(SingleVenueParser):
    """Parser for Mondial du Lion — Le Lion d'Angers, France.

    FEI World Breeding Eventing Championships for Young Horses.
    The premier championship for 6 and 7-year-old event horses,
    held annually at the Haras National du Lion d'Angers in the Loire Valley.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Le Lion d'Angers"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.mondialdulion.com/en/"

    SHOW_NAME = "Mondial du Lion 2026"
    DATE_START = "2026-10-15"
    DATE_END = "2026-10-18"

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
                latitude=47.6300,
                longitude=-0.7000,
                url=url,
            )
        ]
        self._log_result("Mondial du Lion", len(events))
        return events
