from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("fontainebleau")
class FontainebleauParser(SingleVenueParser):
    """Parser for Fontainebleau — Grand Parquet, Fontainebleau, France.

    CDIO5*/CSI5* held at the Grand Parquet equestrian complex near the
    Chateau de Fontainebleau. Major dual-discipline event featuring both
    5-star dressage and show jumping over two weekends.
    Static parser: dates are hard-coded and updated annually.
    """

    VENUE_NAME = "Grand Parquet, Fontainebleau"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.grandparquet.com/"

    SHOW_NAME = "Grand Parquet Fontainebleau 2026"
    DATE_START = "2026-04-16"
    DATE_END = "2026-04-26"

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
                discipline=None,  # Multi-discipline: dressage + SJ
                event_type="show",
                latitude=48.4167,
                longitude=2.7000,
                url=url,
            )
        ]
        self._log_result("Fontainebleau", len(events))
        return events
