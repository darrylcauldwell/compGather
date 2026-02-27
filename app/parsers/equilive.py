from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.parsers.bases import HttpParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

SINGLE_DATE_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)\s+(January|February|March|April|May|June|"
    r"July|August|September|October|November|December),?\s+(\d{4})",
    re.IGNORECASE,
)

RANGE_SAME_MONTH_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)\s*-\s*(\d{1,2})(?:st|nd|rd|th)\s+"
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December),?\s+(\d{4})",
    re.IGNORECASE,
)

RANGE_CROSS_MONTH_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)\s+(January|February|March|April|May|June|"
    r"July|August|September|October|November|December)\s*-\s*"
    r"(\d{1,2})(?:st|nd|rd|th)\s+(January|February|March|April|May|June|"
    r"July|August|September|October|November|December),?\s+(\d{4})",
    re.IGNORECASE,
)


@register_parser("equilive")
class EquiLiveParser(HttpParser):
    """Parser for equilive.uk/events — server-rendered single page with all upcoming events."""

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        async with self._make_client() as client:
            html = await self._fetch_text(client, url)

        soup = BeautifulSoup(html, "html.parser")
        competitions = []

        name_tags = soup.find_all("p", style=re.compile(r"font-size:\s*17px"))
        venue_tags = soup.find_all("p", style=re.compile(r"font-size:\s*15px"))
        date_tags = soup.find_all("p", style=re.compile(r"font-size:\s*13px"))

        count = min(len(name_tags), len(venue_tags), len(date_tags))
        logger.info("EquiLive: found %d event cards", count)

        for i in range(count):
            name = name_tags[i].get_text(strip=True)
            venue = venue_tags[i].get_text(strip=True)
            date_text = date_tags[i].get_text(strip=True)

            if not name or not date_text:
                continue

            date_start, date_end = self._parse_date_range(date_text)
            if not date_start:
                continue

            event_url = None
            parent = name_tags[i].find_parent()
            if parent:
                link = parent.find_parent().find("a", href=re.compile(r"equilive\.uk/events/"))
                if link:
                    event_url = link["href"]

            discipline = None

            competitions.append(self._build_event(
                name=name,
                date_start=date_start,
                date_end=date_end if date_end and date_end != date_start else None,
                venue_name=venue,
                discipline=discipline,
                url=event_url or url,
            ))

        self._log_result("EquiLive", len(competitions))
        return competitions

    def _parse_date_range(self, text):
        m = RANGE_CROSS_MONTH_RE.search(text)
        if m:
            try:
                start = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(5)}", "%d %B %Y")
                end = datetime.strptime(f"{m.group(3)} {m.group(4)} {m.group(5)}", "%d %B %Y")
                return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
            except ValueError:
                pass

        m = RANGE_SAME_MONTH_RE.search(text)
        if m:
            try:
                start = datetime.strptime(f"{m.group(1)} {m.group(3)} {m.group(4)}", "%d %B %Y")
                end = datetime.strptime(f"{m.group(2)} {m.group(3)} {m.group(4)}", "%d %B %Y")
                return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
            except ValueError:
                pass

        m = SINGLE_DATE_RE.search(text)
        if m:
            try:
                dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y")
                return dt.strftime("%Y-%m-%d"), None
            except ValueError:
                pass

        return None, None
