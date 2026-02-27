from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("old_salem_farm")
class OldSalemFarmParser(SingleVenueParser):
    """Parser for Old Salem Farm — North Salem, NY.

    Two spring CSI3* shows plus the American Gold Cup CSI4*-W World Cup
    qualifier in autumn. Historic venue in Westchester County.
    Static parser with multi-fixture output.
    """

    VENUE_NAME = "Old Salem Farm, North Salem"
    VENUE_POSTCODE = None
    BASE_URL = "https://oldsalemfarm.net/"

    FIXTURES = [
        ("Old Salem Farm Spring CSI3* Week 1", "2026-05-12", "2026-05-17"),
        ("Old Salem Farm Spring CSI3* Week 2", "2026-05-19", "2026-05-24"),
        ("American Gold Cup CSI4*-W 2026", "2026-09-24", "2026-09-27"),
    ]

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("Old Salem Farm: site unreachable, returning static data")

        events = [
            self._build_event(
                name=name,
                date_start=start,
                date_end=end,
                discipline="Show Jumping",
                event_type="competition",
                latitude=41.3346,
                longitude=-73.5779,
                url=url,
            )
            for name, start, end in self.FIXTURES
        ]
        self._log_result("Old Salem Farm", len(events))
        return events
