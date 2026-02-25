"""Parser for HPA (Hurlingham Polo Association) polo fixtures.

Uses the Sport80 public widget JSON API to fetch fixture data.
The API at hpa.sport80.com/api/public/widget/data/new/1 returns
paginated fixture results.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from app.parsers.bases import HttpParser
from app.parsers.registry import register_parser
from app.parsers.utils import extract_postcode, normalise_postcode
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

API_URL = "https://hpa.sport80.com/api/public/widget/data/new/1"
WIDGET_URL = "https://hpa.sport80.com/public/widget/1"

DATE_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+"
    r"(\d{4})",
    re.IGNORECASE,
)


@register_parser("hpa_polo")
class HPAPoloParser(HttpParser):
    """Parser for HPA polo fixtures via Sport80 JSON API.

    Fetches paginated fixture data from the Sport80 public widget API.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        competitions: list[ExtractedEvent] = []
        seen: set[tuple[str, str]] = set()

        async with self._make_client() as client:
            page = 0
            while True:
                data = await self._fetch_json(
                    client,
                    API_URL,
                    params={"p": str(page), "i": "50", "s": "", "l": "", "d": "0", "f": ""},
                )

                total = int(data.get("total", 0))
                items = data.get("data", [])
                logger.info("HPA Polo: page %d, %d items (total %d)", page, len(items), total)

                for item in items:
                    comp = self._parse_fixture(item)
                    if comp:
                        key = (comp.name, comp.date_start)
                        if key not in seen:
                            seen.add(key)
                            competitions.append(comp)

                next_url = data.get("next_page_url")
                if not next_url or not items:
                    break
                page += 1

        self._log_result("HPA Polo", len(competitions))
        return competitions

    def _parse_fixture(self, item: dict) -> ExtractedEvent | None:
        """Parse a single fixture from the Sport80 API response."""
        name = item.get("name", "").strip()
        if not name or len(name) < 3:
            return None

        # Try to parse date from the item
        date_start = None
        for date_field in ["start_date", "date", "event_date", "from_date"]:
            raw = item.get(date_field, "")
            if raw:
                date_start = self._parse_date(raw)
                if date_start:
                    break

        # Fallback: try extracting date from the name or description
        if not date_start:
            text = f"{name} {item.get('description', '')}"
            m = DATE_RE.search(text)
            if m:
                date_start = self._parse_date_match(m)

        if not date_start:
            return None

        date_end = None
        for end_field in ["end_date", "to_date"]:
            raw = item.get(end_field, "")
            if raw:
                date_end = self._parse_date(raw)
                if date_end:
                    break

        venue_name = item.get("venue", item.get("location", "HPA Polo"))
        if isinstance(venue_name, dict):
            venue_name = venue_name.get("name", "HPA Polo")
        venue_name = str(venue_name).strip() or "HPA Polo"

        venue_postcode = None
        address = item.get("address", item.get("postcode", ""))
        if address:
            venue_postcode = extract_postcode(str(address))
            if venue_postcode:
                venue_postcode = normalise_postcode(venue_postcode)

        event_url = item.get("url", WIDGET_URL)
        if not event_url or not event_url.startswith("http"):
            event_url = WIDGET_URL

        return self._build_event(
            name=name[:100],
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name=venue_name[:100],
            venue_postcode=venue_postcode,
            discipline="Polo",
            url=event_url,
        )

    def _parse_date_match(self, match):
        try:
            day = match.group(1)
            month = match.group(2)[:3]
            year = match.group(3)
            dt = datetime.strptime(f"{day} {month} {year}", "%d %b %Y")
            return dt.strftime("%Y-%m-%d")
        except (ValueError, IndexError, AttributeError):
            return None
