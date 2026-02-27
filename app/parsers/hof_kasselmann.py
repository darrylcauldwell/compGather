from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("hof_kasselmann")
class HofKasselmannParser(SingleVenueParser):
    """Parser for Hof Kasselmann — Hagen am Teutoburger Wald, Germany.

    Historic 40-hectare facility hosting CDI5*/CSI4* and Nations Cup events.
    Home of the "Horses & Dreams" series.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Hof Kasselmann"
    VENUE_POSTCODE = None
    BASE_URL = "https://horses-and-dreams.de/en/"

    # Update annually — 2026 fixtures
    FIXTURES = [
        ("Horses & Dreams 2026", "2026-04-22", "2026-04-26"),
        ("Nations Cup Hagen 2026", "2026-07-01", "2026-07-05"),
    ]

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("Hof Kasselmann: site unreachable, returning static data")

        events = [
            self._build_event(
                name=name,
                date_start=start,
                date_end=end,
                discipline="Show Jumping",
                event_type="show",
                latitude=52.1972,
                longitude=7.9782,
                url=url,
            )
            for name, start, end in self.FIXTURES
        ]
        self._log_result("Hof Kasselmann", len(events))
        return events
