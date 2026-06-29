from __future__ import annotations

import json
import logging
import re

from bs4 import BeautifulSoup

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.parsers.utils import continental_discipline, continental_event_type, prefix_venue
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("sentower_park")
class SentowerParkParser(SingleVenueParser):
    """Sentower Park (Oudsbergen, BE) — Wix Events, server-hydrated.

    The events list ships in the page's ``wix-warmup-data`` JSON blob (no JS
    needed). Fixtures mix enterable youth/1*/YH classes with elite CSI/CDI, so
    event_type is decided per event. Outdoor/Indoor "Training" entries are
    schooling, not competitions, and are skipped.
    """

    VENUE_NAME = "Sentower Park"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.sentowerpark.com"
    EVENTS_URL = "https://www.sentowerpark.com/events"
    LABEL = "Sentower"
    # Non-competition listings that share the events feed (schooling, social).
    SKIP = ("training", "village", "car event")

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        async with self._make_client() as client:
            html = await self._fetch_text(client, self.EVENTS_URL)

        soup = BeautifulSoup(html, "html.parser")
        warm = soup.find(id="wix-warmup-data")
        if not warm or not warm.string:
            self._log_result("Sentower Park", 0)
            return []

        raw = self._find_events(json.loads(warm.string)) or []
        events: list[ExtractedEvent] = []
        for ev in raw:
            title = (ev.get("title") or "").strip()
            if not title or any(s in title.lower() for s in self.SKIP):
                continue
            sched = (ev.get("scheduling") or {}).get("config") or {}
            date_start = (sched.get("startDate") or "")[:10]
            if not re.match(r"\d{4}-\d{2}-\d{2}", date_start):
                continue
            date_end = (sched.get("endDate") or "")[:10]
            if date_end == date_start:
                date_end = None

            coords = (ev.get("location") or {}).get("coordinates") or {}
            slug = ev.get("slug")
            href = f"{self.BASE_URL}/details-en-registratie/{slug}" if slug else self.EVENTS_URL

            events.append(
                self._build_event(
                    name=prefix_venue(title, self.LABEL),
                    date_start=date_start,
                    date_end=date_end,
                    latitude=coords.get("lat"),
                    longitude=coords.get("lng"),
                    discipline=continental_discipline(title),
                    event_type=continental_event_type(title),
                    url=href,
                )
            )

        events = self._dedup(events)
        self._log_result("Sentower Park", len(events))
        return events

    @classmethod
    def _find_events(cls, obj):
        """Recursively locate the Wix Events ``events.events`` list."""
        if isinstance(obj, dict):
            inner = obj.get("events")
            if isinstance(inner, dict) and isinstance(inner.get("events"), list):
                return inner["events"]
            for v in obj.values():
                found = cls._find_events(v)
                if found:
                    return found
        elif isinstance(obj, list):
            for v in obj:
                found = cls._find_events(v)
                if found:
                    return found
        return None
