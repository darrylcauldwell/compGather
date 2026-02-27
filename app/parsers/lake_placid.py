from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("lake_placid")
class LakePlacidParser(SingleVenueParser):
    """Parser for Lake Placid Horse Shows — Lake Placid, NY.

    Two consecutive weeks of CSI3* competition in the Adirondacks:
    Lake Placid Horse Show followed by I Love New York Horse Show.
    Static parser with multi-fixture output.
    """

    VENUE_NAME = "Lake Placid Horse Show Grounds"
    VENUE_POSTCODE = None
    BASE_URL = "https://lakeplacidhorseshow.com/"

    FIXTURES = [
        ("Lake Placid Horse Show CSI3* 2026", "2026-06-23", "2026-06-28"),
        ("I Love New York Horse Show CSI3* 2026", "2026-06-30", "2026-07-05"),
    ]

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("Lake Placid: site unreachable, returning static data")

        events = [
            self._build_event(
                name=name,
                date_start=start,
                date_end=end,
                discipline="Show Jumping",
                event_type="competition",
                latitude=44.2779,
                longitude=-73.9546,
                url=url,
            )
            for name, start, end in self.FIXTURES
        ]
        self._log_result("Lake Placid", len(events))
        return events
