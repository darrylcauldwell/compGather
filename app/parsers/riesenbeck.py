from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("riesenbeck")
class RiesenbeckParser(SingleVenueParser):
    """Parser for Riesenbeck International — Hörstel-Riesenbeck, Münsterland, Germany.

    Ludger Beerbaum's world-class facility hosting multiple CSI events per year.
    The LGCT stop is covered by the lgct parser; this covers standalone events.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Riesenbeck International"
    VENUE_POSTCODE = None
    BASE_URL = "https://riesenbeck-international.com/en/"

    # Update annually — non-LGCT CSI events at Riesenbeck
    FIXTURES = [
        ("Riesenbeck International CSI February", "2026-02-04", "2026-02-08"),
        ("Riesenbeck International CSI May", "2026-05-21", "2026-05-24"),
    ]

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("Riesenbeck: site unreachable, returning static data")

        events = [
            self._build_event(
                name=name,
                date_start=start,
                date_end=end,
                discipline="Show Jumping",
                event_type="competition",
                latitude=52.2530,
                longitude=7.5974,
                url=url,
            )
            for name, start, end in self.FIXTURES
        ]
        self._log_result("Riesenbeck", len(events))
        return events
