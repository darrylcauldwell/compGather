from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("saut_hermes")
class SautHermesParser(SingleVenueParser):
    """Parser for Saut Hermès — Grand Palais, Paris, France.

    Prestigious CSI5* invitation-only show jumping event under the glass
    roof of the Grand Palais, organised by Hermès.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Grand Palais, Paris"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.sauthermes.com/en/"

    SHOW_NAME = "Saut Hermès 2026"
    DATE_START = "2026-03-20"
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
                discipline="Show Jumping",
                event_type="show",
                latitude=48.8661,
                longitude=2.3122,
                url=url,
            )
        ]
        self._log_result("Saut Hermès", len(events))
        return events
