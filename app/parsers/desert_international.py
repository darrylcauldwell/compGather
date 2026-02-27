from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("desert_international")
class DesertInternationalParser(SingleVenueParser):
    """Parser for Desert International Horse Park — Thermal, CA.

    Premier West Coast winter circuit. CSI2*-5*-W including FEI World Cup
    North American League qualifiers. Multiple weeks of international
    competition in the Coachella Valley.
    Static parser with multi-fixture output (key weeks).
    """

    VENUE_NAME = "Desert International Horse Park, Thermal"
    VENUE_POSTCODE = None
    BASE_URL = "https://deserthorsepark.com/"

    FIXTURES = [
        ("Desert Circuit 1 — CSI3*", "2026-01-06", "2026-01-11"),
        ("Desert Circuit 2 — CSI4*", "2026-01-13", "2026-01-18"),
        ("Desert Circuit 3 — CSI5*", "2026-01-20", "2026-01-25"),
        ("Desert Circuit 4 — CSI5*-W World Cup", "2026-01-27", "2026-02-01"),
        ("Desert Circuit 5 — CSI3*", "2026-02-03", "2026-02-08"),
        ("Desert Circuit 6 — CSI3*", "2026-02-10", "2026-02-15"),
    ]

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("Desert International: site unreachable, returning static data")

        events = [
            self._build_event(
                name=name,
                date_start=start,
                date_end=end,
                discipline="Show Jumping",
                event_type="competition",
                latitude=33.6150,
                longitude=-116.1400,
                url=url,
            )
            for name, start, end in self.FIXTURES
        ]
        self._log_result("Desert International", len(events))
        return events
