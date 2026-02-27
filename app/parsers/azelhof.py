from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("azelhof")
class AzelhofParser(SingleVenueParser):
    """Parser for Azelhof Horse Events — Lier (Koningshooikt), Belgium.

    Major indoor winter/spring show jumping circuit running Nov-Mar each season.
    Hosts CSI2*/1*/YH level competitions across multiple weekly tours.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Azelhof"
    VENUE_POSTCODE = None
    BASE_URL = "https://azelhof.be/en/home/"

    # Update annually — 2025-2026 winter/spring season
    FIXTURES = [
        ("Azelhof Autumn Tour Week 1", "2025-11-05", "2025-11-09"),
        ("Azelhof X-Mas Tour Week 1", "2025-12-03", "2025-12-07"),
        ("Azelhof X-Mas Tour Week 2", "2025-12-09", "2025-12-14"),
        ("Azelhof New Year Tour", "2026-01-15", "2026-01-18"),
        ("Azelhof Winter Tour", "2026-02-04", "2026-02-08"),
        ("Azelhof CDI Lier", "2026-02-24", "2026-03-01"),
        ("Azelhof Spring Tour Week 1", "2026-03-12", "2026-03-15"),
        ("Azelhof Spring Tour Week 2", "2026-03-18", "2026-03-22"),
        ("Azelhof Spring Tour Week 3", "2026-03-25", "2026-03-29"),
    ]

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("Azelhof: site unreachable, returning static data")

        events = [
            self._build_event(
                name=name,
                date_start=start,
                date_end=end,
                discipline="Show Jumping",
                event_type="competition",
                latitude=51.1310,
                longitude=4.5700,
                url=url,
            )
            for name, start, end in self.FIXTURES
        ]
        self._log_result("Azelhof", len(events))
        return events
