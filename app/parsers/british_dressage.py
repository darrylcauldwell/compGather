from __future__ import annotations

import html
import json
import logging
from pathlib import Path

from app.parsers.bases import HttpParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

API_URL = "https://britishdressage.online/api/events/getByPublicFilter"
DETAIL_URL = "https://britishdressage.online/schedule/{id}"
SEED_FILE = Path(__file__).parent / "british_dressage_seed.json"

CANCELLED_STATUS = 5


@register_parser("british_dressage")
class BritishDressageParser(HttpParser):
    """Parser for britishdressage.online — JSON API.

    Single POST request returns all events (~1,300) as structured JSON.
    No authentication or pagination required.
    """

    TIMEOUT = 60.0

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
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

            competitions: list[ExtractedEvent] = []
            for row in rows:
                comp = self._row_to_competition(row)
                if comp:
                    competitions.append(comp)

            self._log_result("British Dressage", len(competitions))
            return competitions
        except Exception:
            logger.warning("British Dressage API unavailable, falling back to seed file")
            return self._load_seed()

    def _row_to_competition(self, row: dict) -> ExtractedEvent | None:
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

        date_start = self._parse_date(start)
        date_end = self._parse_date(end)
        if not date_start:
            return None

        class_range = row.get("class_range", "") or ""
        classes = [c.strip() for c in class_range.split("+") if c.strip()] if class_range else []

        event_id = row.get("id")
        detail_url = DETAIL_URL.format(id=event_id) if event_id else None

        return self._build_event(
            name=name,
            date_start=date_start,
            date_end=date_end if date_end != date_start else None,
            venue_name=venue_name or "TBC",
            discipline="Dressage",
            classes=classes,
            url=detail_url or "https://britishdressage.online/",
        )

    def _load_seed(self) -> list[ExtractedEvent]:
        if not SEED_FILE.exists():
            logger.error("British Dressage seed file not found: %s", SEED_FILE)
            return []
        rows = json.loads(SEED_FILE.read_text())
        competitions: list[ExtractedEvent] = []
        for row in rows:
            date_start = row.get("date_start")
            if not date_start:
                continue
            competitions.append(self._build_event(
                name=row["name"],
                date_start=date_start,
                date_end=row.get("date_end"),
                venue_name=row.get("venue_name") or "TBC",
                venue_postcode=row.get("venue_postcode"),
                latitude=row.get("latitude"),
                longitude=row.get("longitude"),
                discipline=row.get("discipline", "Dressage"),
                classes=[],
                url=row.get("url"),
            ))
        logger.info("British Dressage: loaded %d competitions from seed file", len(competitions))
        return competitions
