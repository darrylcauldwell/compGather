from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("osberton")
class OsbertonParser(SingleVenueParser):
    """Parser for Osberton International Horse Trials — Osberton Estate, Worksop.

    Two international eventing fixtures per year, run by BEDE Events.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Osberton"
    VENUE_POSTCODE = "S80 2LW"
    BASE_URL = "https://osbertonhorse.co.uk"

    # Update annually — two fixtures in 2026
    FIXTURES = [
        ("Osberton International Horse Trials (1) 2026", "2026-05-22", "2026-05-24"),
        ("Osberton International Horse Trials (2) 2026", "2026-10-02", "2026-10-04"),
    ]

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("Osberton: site unreachable, returning static data")

        events = [
            self._build_event(
                name=name,
                date_start=start,
                date_end=end,
                discipline="Eventing",
                event_type="show",
                url=url,
            )
            for name, start, end in self.FIXTURES
        ]
        self._log_result("Osberton", len(events))
        return events
