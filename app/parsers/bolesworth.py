from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("bolesworth")
class BolesworthParser(SingleVenueParser):
    """Parser for Bolesworth International — Bolesworth Castle, Cheshire, UK.

    CSI4* international show jumping held over two weeks at Bolesworth Castle.
    Also hosts dressage and young horse classes. One of the UK's premier
    outdoor international equestrian events.
    Static parser with multi-fixture output.
    """

    VENUE_NAME = "Bolesworth Castle"
    VENUE_POSTCODE = "SY14 8DD"
    BASE_URL = "https://www.bolesworth.com/"

    FIXTURES = [
        ("Bolesworth International CSI4* Week 1", "2026-06-25", "2026-06-28"),
        ("Bolesworth International CSI4* Week 2", "2026-07-02", "2026-07-05"),
    ]

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("Bolesworth: site unreachable, returning static data")

        events = [
            self._build_event(
                name=name,
                date_start=start,
                date_end=end,
                discipline="Show Jumping",
                event_type="competition",
                latitude=53.0975,
                longitude=-2.7175,
                url=url,
            )
            for name, start, end in self.FIXTURES
        ]
        self._log_result("Bolesworth", len(events))
        return events
