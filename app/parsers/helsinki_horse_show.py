from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("helsinki_horse_show")
class HelsinkiHorseShowParser(SingleVenueParser):
    """Parser for Helsinki International Horse Show — Messukeskus, Helsinki, Finland.

    CSI5*-W World Cup qualifier. One of the biggest indoor equestrian events
    in the Nordics, held at the Helsinki Exhibition and Convention Centre.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Messukeskus, Helsinki"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.horseshowhelsinki.fi/en/"

    SHOW_NAME = "Helsinki International Horse Show 2026"
    DATE_START = "2026-10-22"
    DATE_END = "2026-10-25"

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("%s: site unreachable, returning static data", self.SHOW_NAME)

        events = [
            self._build_event(
                name=self.SHOW_NAME,
                date_start=self.DATE_START,
                date_end=self.DATE_END,
                discipline="Show Jumping",
                event_type="show",
                latitude=60.2058,
                longitude=24.9292,
                url=url,
            )
        ]
        self._log_result("Helsinki Horse Show", len(events))
        return events
