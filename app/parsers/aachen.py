from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("aachen")
class AachenParser(SingleVenueParser):
    """Parser for Aachen World Equestrian Festival — Aachen Soers, Germany.

    In 2026 Aachen hosts two major fixtures:
    1. TSCHIO Aachen (traditional CHIO moved to May as a one-off)
    2. FEI World Championships Aachen (six disciplines, Aug)
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Aachen Soers"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.chioaachen.de/en/"

    # Update annually — two fixtures in 2026
    FIXTURES = [
        ("TSCHIO Aachen 2026", "2026-05-22", "2026-05-24"),
        ("FEI World Championships Aachen 2026", "2026-08-11", "2026-08-23"),
    ]

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("Aachen: site unreachable, returning static data")

        events = [
            self._build_event(
                name=name,
                date_start=start,
                date_end=end,
                discipline=None,
                event_type="show",
                latitude=50.7933,
                longitude=6.0972,
                url=url,
            )
            for name, start, end in self.FIXTURES
        ]
        self._log_result("Aachen", len(events))
        return events
