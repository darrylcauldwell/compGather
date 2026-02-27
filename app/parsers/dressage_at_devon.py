from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("dressage_at_devon")
class DressageAtDevonParser(SingleVenueParser):
    """Parser for Dressage at Devon — Devon, PA.

    One of the highest-rated international dressage competitions in the US.
    CDI plus breed show. Held at the same grounds as Devon Horse Show.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Devon Horse Show Grounds"
    VENUE_POSTCODE = None
    BASE_URL = "https://dressageatdevon.org/"

    SHOW_NAME = "Dressage at Devon 2026"
    DATE_START = "2026-09-22"
    DATE_END = "2026-09-27"

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
                discipline="Dressage",
                event_type="show",
                latitude=40.0474,
                longitude=-75.4198,
                url=url,
            )
        ]
        self._log_result("Dressage at Devon", len(events))
        return events
