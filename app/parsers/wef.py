from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("wef")
class WEFParser(SingleVenueParser):
    """Parser for Winter Equestrian Festival — Wellington International, FL.

    The largest and longest-running horse show in the world. 13 weeks of
    competition from CSI2* to CSI5*, culminating in the $1M Rolex Grand Prix.
    Record $16M total prize money for 2026.
    Static parser with multi-fixture output (one event per week).
    """

    VENUE_NAME = "Wellington International"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.wellingtoninternational.com/"

    FIXTURES = [
        ("WEF Week 1 — CSI2*/CSI3*", "2025-12-31", "2026-01-04"),
        ("WEF Week 2 — CSI2*/CSI3*", "2026-01-07", "2026-01-11"),
        ("WEF Week 3 — CSI3*/CSI4*", "2026-01-14", "2026-01-18"),
        ("WEF Week 4 — CSI3*/CSI4*", "2026-01-21", "2026-01-25"),
        ("WEF Week 5 — CSI4*", "2026-01-28", "2026-02-01"),
        ("WEF Week 6 — CSI3*/CSI4*", "2026-02-04", "2026-02-08"),
        ("WEF Week 7 — CSI4*/CSI5*", "2026-02-11", "2026-02-15"),
        ("WEF Week 8 — CSI5*", "2026-02-18", "2026-02-22"),
        ("WEF Week 9 — CSI4*/CSI5*", "2026-02-25", "2026-03-01"),
        ("WEF Week 10 — CSI4*", "2026-03-04", "2026-03-08"),
        ("WEF Week 11 — CSI3*/CSI5*", "2026-03-11", "2026-03-15"),
        ("WEF Week 12 — CSI5*", "2026-03-18", "2026-03-22"),
        ("WEF Week 13 — CSI5* Grand Finale", "2026-03-25", "2026-03-29"),
    ]

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("WEF: site unreachable, returning static data")

        events = [
            self._build_event(
                name=name,
                date_start=start,
                date_end=end,
                discipline="Show Jumping",
                event_type="competition",
                latitude=26.6588,
                longitude=-80.2414,
                url=url,
            )
            for name, start, end in self.FIXTURES
        ]
        self._log_result("WEF", len(events))
        return events
