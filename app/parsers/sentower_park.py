from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("sentower_park")
class SentowerParkParser(SingleVenueParser):
    """Parser for Sentower Park — Oudsbergen (Opglabbeek), Belgium.

    Major indoor show jumping venue hosting CSI2*/1*/YH to CSI4* level
    competitions throughout the winter season, including the prestigious
    Zangersheide International.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Sentower Park"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.sentowerpark.com/en/home/"

    # Update annually — 2025-2026 winter season
    FIXTURES = [
        ("Sentower Park CSI November", "2025-11-27", "2025-11-30"),
        ("Sentower Park Happy New Year CSI", "2025-12-19", "2025-12-21"),
        ("Sentower Park CSI January", "2026-01-27", "2026-02-01"),
        ("Zangersheide International", "2026-02-25", "2026-03-01"),
    ]

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("Sentower Park: site unreachable, returning static data")

        events = [
            self._build_event(
                name=name,
                date_start=start,
                date_end=end,
                discipline="Show Jumping",
                event_type="competition",
                latitude=51.0470,
                longitude=5.5880,
                url=url,
            )
            for name, start, end in self.FIXTURES
        ]
        self._log_result("Sentower Park", len(events))
        return events
