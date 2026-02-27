from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("pau")
class PauParser(SingleVenueParser):
    """Parser for Les 5 Etoiles de Pau — CCI5*-L eventing, Pau, France.

    One of only seven CCI5* events worldwide.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Domaine de Sers, Pau"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.event-pau.com"

    SHOW_NAME = "Les 5 Etoiles de Pau 2026"
    DATE_START = "2026-10-22"
    DATE_END = "2026-10-25"

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
                latitude=43.2951,
                longitude=-0.3708,
                url=url,
            )
        ]
        self._log_result("Pau", len(events))
        return events
