from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("toscana_tour")
class ToscanaTourParser(SingleVenueParser):
    """Parser for Toscana Tour — Arezzo Equestrian Centre, Arezzo, Italy.

    CSI2*-4* spring tour over 4 weeks at the Arezzo Equestrian Centre in
    Tuscany. One of the most popular spring competition tours in continental
    Europe, attracting riders from across the continent.
    Static parser with multi-fixture output.
    """

    VENUE_NAME = "Arezzo Equestrian Centre"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.toscanatour.com/"

    FIXTURES = [
        ("Toscana Tour Week 1 — CSI2*/CSI3*", "2026-03-17", "2026-03-22"),
        ("Toscana Tour Week 2 — CSI2*/CSI3*", "2026-03-24", "2026-03-29"),
        ("Toscana Tour Week 3 — CSI3*/CSI4*", "2026-03-31", "2026-04-05"),
        ("Toscana Tour Week 4 — CSI3*/CSI4*", "2026-04-07", "2026-04-12"),
    ]

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("Toscana Tour: site unreachable, returning static data")

        events = [
            self._build_event(
                name=name,
                date_start=start,
                date_end=end,
                discipline="Show Jumping",
                event_type="competition",
                latitude=43.4617,
                longitude=11.8819,
                url=url,
            )
            for name, start, end in self.FIXTURES
        ]
        self._log_result("Toscana Tour", len(events))
        return events
