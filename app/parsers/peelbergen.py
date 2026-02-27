from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("peelbergen")
class PeelbergenParser(SingleVenueParser):
    """Parser for Peelbergen Equestrian Centre — Kronenberg, Limburg, Netherlands.

    Year-round CSI venue near the German/Belgian border. Selected to host
    the Longines EEF Series Semifinal (Regions West/North) from 2026 to 2030.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Peelbergen Equestrian Centre"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.peelbergen.eu/"

    # Update annually — 2026 key CSI events
    FIXTURES = [
        ("Peelbergen CSI February", "2026-02-16", "2026-02-22"),
        ("Peelbergen EEF Series Semifinal", "2026-07-02", "2026-07-05"),
    ]

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("Peelbergen: site unreachable, returning static data")

        events = [
            self._build_event(
                name=name,
                date_start=start,
                date_end=end,
                discipline="Show Jumping",
                event_type="competition",
                latitude=51.3640,
                longitude=6.1100,
                url=url,
            )
            for name, start, end in self.FIXTURES
        ]
        self._log_result("Peelbergen", len(events))
        return events
