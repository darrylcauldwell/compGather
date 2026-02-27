from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("vilamoura")
class VilamouraParser(SingleVenueParser):
    """Parser for Vilamoura Classic — Vilamoura Equestrian Centre, Algarve, Portugal.

    Formerly the Atlantic Tour / Champions Tour, rebranded as Vilamoura Classic
    in 2026 under GRANDPRIX Events. Spring 2026 tours cancelled; autumn confirmed.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Vilamoura Equestrian Centre"
    VENUE_POSTCODE = None
    BASE_URL = "https://grandprix-events.com/en/vilamoura-classic/"

    # Update annually — 2026 autumn season (spring cancelled)
    FIXTURES = [
        ("Vilamoura Classic Tour II Week 1", "2026-10-20", "2026-10-25"),
        ("Vilamoura Classic Tour II Week 2", "2026-10-27", "2026-11-01"),
        ("Vilamoura Classic Tour II Week 3", "2026-11-03", "2026-11-08"),
        ("Vilamoura Classic Tour III Week 1", "2026-11-17", "2026-11-22"),
        ("Vilamoura Classic Tour III Week 2", "2026-11-24", "2026-11-29"),
        ("Vilamoura Classic Tour III Week 3", "2026-12-01", "2026-12-06"),
    ]

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("Vilamoura Classic: site unreachable, returning static data")

        events = [
            self._build_event(
                name=name,
                date_start=start,
                date_end=end,
                discipline="Show Jumping",
                event_type="competition",
                latitude=37.1040,
                longitude=-8.1250,
                url=url,
            )
            for name, start, end in self.FIXTURES
        ]
        self._log_result("Vilamoura Classic", len(events))
        return events
