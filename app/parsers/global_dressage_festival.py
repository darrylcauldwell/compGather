from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("global_dressage_festival")
class GlobalDressageFestivalParser(SingleVenueParser):
    """Parser for Adequan Global Dressage Festival — Wellington, FL.

    10 weeks of international dressage at Equestrian Village, running
    concurrently with WEF. Includes CDI-W World Cup qualifiers and the
    Palm Beach Dressage Derby. $550,000+ in prize money.
    Static parser with multi-fixture output (one event per week).
    """

    VENUE_NAME = "Equestrian Village, Wellington"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.globaldressagefestival.com/"

    FIXTURES = [
        ("GDF Week 1 — CDI3*/National", "2026-01-07", "2026-01-11"),
        ("GDF Week 2 — CDI3*", "2026-01-14", "2026-01-18"),
        ("GDF Week 3 — CDI-W World Cup Qualifier", "2026-01-21", "2026-01-25"),
        ("GDF Week 4 — CDI3*/CDI4*", "2026-01-28", "2026-02-01"),
        ("GDF Week 5 — CDI3*/CDI4*", "2026-02-04", "2026-02-08"),
        ("GDF Week 6 — CDI4*/CDI-W", "2026-02-11", "2026-02-15"),
        ("GDF Week 7 — CDI4*", "2026-02-18", "2026-02-22"),
        ("GDF Week 8 — CDI5* Palm Beach Derby", "2026-02-25", "2026-03-01"),
        ("GDF Week 9 — CDI3*", "2026-03-04", "2026-03-08"),
        ("GDF Week 10 — CDI4*/CDI-W Finale", "2026-03-18", "2026-03-22"),
    ]

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("GDF: site unreachable, returning static data")

        events = [
            self._build_event(
                name=name,
                date_start=start,
                date_end=end,
                discipline="Dressage",
                event_type="competition",
                latitude=26.6530,
                longitude=-80.2525,
                url=url,
            )
            for name, start, end in self.FIXTURES
        ]
        self._log_result("Global Dressage Festival", len(events))
        return events
