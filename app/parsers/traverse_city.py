from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("traverse_city")
class TraverseCityParser(SingleVenueParser):
    """Parser for Traverse City Horse Shows / Great Lakes Equestrian Festival.

    Flintfields Horse Park, Williamsburg, MI. 13 weeks of summer competition
    from CSI3* to CSI5*, including FEI World Cup North American League
    qualifier in September. Major League Show Jumping venue.
    Static parser with multi-fixture output (key weeks).
    """

    VENUE_NAME = "Flintfields Horse Park, Traverse City"
    VENUE_POSTCODE = None
    BASE_URL = "https://traversecityhorseshows.com/"

    FIXTURES = [
        ("Traverse City Spring I — CSI3*", "2026-06-02", "2026-06-07"),
        ("Traverse City Spring II — CSI3*", "2026-06-09", "2026-06-14"),
        ("GLEF Week I — CSI3*", "2026-06-23", "2026-06-28"),
        ("GLEF Week II — CSI4*", "2026-06-30", "2026-07-05"),
        ("GLEF Week III — CSI4*/CSI5*", "2026-07-07", "2026-07-12"),
        ("GLEF Week IV — CSI5*", "2026-07-14", "2026-07-19"),
        ("Traverse City Summer — CSI3*", "2026-08-04", "2026-08-09"),
        ("Traverse City Fall International — CSI5*-W", "2026-09-15", "2026-09-20"),
    ]

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("Traverse City: site unreachable, returning static data")

        events = [
            self._build_event(
                name=name,
                date_start=start,
                date_end=end,
                discipline="Show Jumping",
                event_type="competition",
                latitude=44.7631,
                longitude=-85.4115,
                url=url,
            )
            for name, start, end in self.FIXTURES
        ]
        self._log_result("Traverse City", len(events))
        return events
