from __future__ import annotations

import html
import logging
import re
from datetime import datetime

import httpx

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, is_future_event
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

API_URL = "https://britishdressage.online/api/events/getByPublicFilter"
DETAIL_URL = "https://britishdressage.online/schedule/{id}"

# Status codes: 5 = Cancelled, 6 = Verified
CANCELLED_STATUS = 5

# Pony/junior keywords in class_range or show name
PONY_KEYWORDS_BD = [
    "pony", "yr", "jr", "junior", "young horse", "young pony", "yh", "yp",
]


@register_parser("british_dressage")
class BritishDressageParser(BaseParser):
    """Parser for britishdressage.online — JSON API.

    Single POST request returns all events (~1,300) as structured JSON.
    No authentication or pagination required.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
            resp = await client.post(
                API_URL,
                json={},
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        rows = data.get("data", [])
        total = data.get("recordsTotal", len(rows))
        logger.info("British Dressage: %d events from API (total: %d)", len(rows), total)

        competitions: list[ExtractedCompetition] = []
        for row in rows:
            comp = self._row_to_competition(row)
            if comp:
                competitions.append(comp)

        logger.info("British Dressage: extracted %d competitions", len(competitions))
        return competitions

    def _row_to_competition(self, row: dict) -> ExtractedCompetition | None:
        """Convert an API row to an ExtractedCompetition."""
        # Skip cancelled events
        if row.get("event_status_id") == CANCELLED_STATUS:
            return None
        if row.get("status", "").lower() == "cancelled":
            return None

        name = html.unescape(row.get("full_show_name", "")).strip()
        venue_name = html.unescape(row.get("venue_name", "")).strip()
        start = row.get("start", "")
        end = row.get("end", "")

        if not name or not start:
            return None

        date_start = self._parse_datetime(start)
        date_end = self._parse_datetime(end)

        if not date_start:
            return None

        if not is_future_event(date_start, date_end):
            return None

        # Parse class range into classes list
        class_range = row.get("class_range", "") or ""
        classes = [c.strip() for c in class_range.split("+") if c.strip()] if class_range else []

        # Detect pony/junior classes
        check_text = f"{name} {class_range}".lower()
        has_pony = any(kw in check_text for kw in PONY_KEYWORDS_BD)

        # Build detail URL
        event_id = row.get("id")
        detail_url = DETAIL_URL.format(id=event_id) if event_id else None

        return ExtractedCompetition(
            name=name,
            date_start=date_start,
            date_end=date_end if date_end != date_start else None,
            venue_name=venue_name or "TBC",
            venue_postcode=None,  # Not available from listing API
            discipline="Dressage",
            has_pony_classes=has_pony,
            classes=classes,
            url=detail_url,
        )

    def _parse_datetime(self, dt_str: str) -> str | None:
        """Parse 'YYYY-MM-DD HH:MM:SS' to 'YYYY-MM-DD'."""
        if not dt_str:
            return None
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
            try:
                return datetime.strptime(dt_str.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None
