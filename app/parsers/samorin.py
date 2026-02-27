from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("samorin")
class SamorinParser(SingleVenueParser):
    """Parser for Samorin — X-Bionic Sphere, Samorin, Slovakia.

    CSI4*/CSIO events at the state-of-the-art X-Bionic Sphere equestrian
    complex. Modern venue hosting multiple international competitions through
    the year, with both indoor and outdoor arenas.
    Static parser with multi-fixture output.
    """

    VENUE_NAME = "X-Bionic Sphere, Samorin"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.x-bionicsphere.com/en/equestrian/"

    FIXTURES = [
        ("Samorin CSI4* Spring", "2026-04-09", "2026-04-12"),
        ("Samorin CSIO3* Nations Cup", "2026-06-04", "2026-06-07"),
        ("Samorin CSI4* Autumn", "2026-09-17", "2026-09-20"),
    ]

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("Samorin: site unreachable, returning static data")

        events = [
            self._build_event(
                name=name,
                date_start=start,
                date_end=end,
                discipline="Show Jumping",
                event_type="competition",
                latitude=48.0078,
                longitude=17.3139,
                url=url,
            )
            for name, start, end in self.FIXTURES
        ]
        self._log_result("Samorin", len(events))
        return events
