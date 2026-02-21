from __future__ import annotations

import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, infer_discipline, is_future_event
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

# Date patterns: "18th February, 2026" or "19th - 22nd February, 2026"
# or "27th February - 1st March, 2026"
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
class EquiLiveParser(BaseParser):
    """Parser for equilive.uk/events — server-rendered single page with all upcoming events.

    Each event is a card with: event name (17px bold), venue (15px), date (13px muted).
    Links to detail pages at /events/[slug] and entry system at entry.equilive.uk.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        competitions = []

        # Each event has three <p> tags with specific font sizes
        # Name: font-size: 17px; font-weight: 500
        # Venue: font-size: 15px
        # Date: font-size: 13px (with text-muted class)
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

            if not is_future_event(date_start, date_end):
                continue

            # Find the nearest detail link
            event_url = None
            parent = name_tags[i].find_parent()
            if parent:
                link = parent.find_parent().find("a", href=re.compile(r"equilive\.uk/events/"))
                if link:
                    event_url = link["href"]

            discipline = infer_discipline(name) or "Show Jumping"
            has_pony = detect_pony_classes(name)

            competitions.append(ExtractedCompetition(
                name=name,
                date_start=date_start,
                date_end=date_end if date_end and date_end != date_start else None,
                venue_name=venue,
                discipline=discipline,
                has_pony_classes=has_pony,
                url=event_url or url,
            ))

        logger.info("EquiLive: extracted %d competitions", len(competitions))
        return competitions

    def _parse_date_range(self, text: str) -> tuple[str | None, str | None]:
        """Parse date text into (start, end) YYYY-MM-DD strings."""
        # Try cross-month range: "27th February - 1st March, 2026"
        m = RANGE_CROSS_MONTH_RE.search(text)
        if m:
            try:
                start = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(5)}", "%d %B %Y")
                end = datetime.strptime(f"{m.group(3)} {m.group(4)} {m.group(5)}", "%d %B %Y")
                return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Try same-month range: "19th - 22nd February, 2026"
        m = RANGE_SAME_MONTH_RE.search(text)
        if m:
            try:
                start = datetime.strptime(f"{m.group(1)} {m.group(3)} {m.group(4)}", "%d %B %Y")
                end = datetime.strptime(f"{m.group(2)} {m.group(3)} {m.group(4)}", "%d %B %Y")
                return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Try single date: "18th February, 2026"
        m = SINGLE_DATE_RE.search(text)
        if m:
            try:
                dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y")
                return dt.strftime("%Y-%m-%d"), None
            except ValueError:
                pass

        return None, None
