"""Parser for Horse Boarding UK championship dates.

The site (horseboardinguk.org) is a Wix SPA listing championship rounds
held at agricultural shows and game fairs across the UK.  Uses Playwright
to render the page, then extracts events from a Wix repeater widget.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.parsers.bases import PlaywrightParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

CHAMPIONSHIP_URL = "https://www.horseboardinguk.org/championshipdates"

# Date patterns on the page: "April 20th - 21st", "September 6th",
# "September 13th 14th"
_DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?"
    r"(?:\s*[-–]\s*(\d{1,2})(?:st|nd|rd|th)?)?",
    re.IGNORECASE,
)

# Also match "13th 14th" without a dash separator
_DATE_RANGE_NO_DASH_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)",
    re.IGNORECASE,
)

# Year from page heading: "2025 CHAMPIONSHIP DATES"
_YEAR_RE = re.compile(r"(\d{4})\s*CHAMPIONSHIP", re.IGNORECASE)


@register_parser("horse_boarding_uk")
class HorseBoardingUKParser(PlaywrightParser):
    """Parser for Horse Boarding UK championship calendar.

    Renders the Wix SPA with Playwright and extracts championship round
    dates and host venue names from the repeater widget.
    """

    WAIT_STRATEGY = "domcontentloaded"
    EXTRA_WAIT_MS = 8000
    TIMEOUT_MS = 60000

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        html = await self._render_page(CHAMPIONSHIP_URL)
        if not html:
            logger.warning("Horse Boarding UK: no content received")
            return []

        events = self._parse_events(html)
        self._log_result("Horse Boarding UK", len(events))
        return events

    def _parse_events(self, html: str) -> list[ExtractedEvent]:
        soup = BeautifulSoup(html, "html.parser")

        # Extract championship year from heading
        year = self._extract_year(soup)

        # Find repeater items (Wix repeater widget)
        items = soup.find_all("div", class_=re.compile(r"wixui-repeater__item"))
        if not items:
            logger.warning("Horse Boarding UK: no repeater items found")
            return []

        events: list[ExtractedEvent] = []
        seen: set[tuple[str, str]] = set()

        for item in items:
            event = self._parse_item(item, year)
            if event:
                key = (event.name, event.date_start)
                if key not in seen:
                    seen.add(key)
                    events.append(event)

        return events

    def _extract_year(self, soup: BeautifulSoup) -> int:
        """Extract the championship year from the page heading."""
        page_text = soup.get_text()
        match = _YEAR_RE.search(page_text)
        if match:
            return int(match.group(1))
        # Fallback: current year
        return datetime.now().year

    def _parse_item(self, item, year: int) -> ExtractedEvent | None:
        """Parse a single repeater item into an ExtractedEvent."""
        # Get all text segments from wixui-rich-text elements
        rich_texts = item.find_all("div", class_="wixui-rich-text")
        texts = [rt.get_text(strip=True) for rt in rich_texts if rt.get_text(strip=True)]

        if len(texts) < 3:
            return None

        date_text = texts[0]       # e.g. "April 20th - 21st"
        round_text = texts[1]      # e.g. "Round 1"
        venue_text = texts[2]      # e.g. "Thame Country Fair"

        if not date_text or not venue_text:
            return None

        # Parse dates
        date_start, date_end = self._parse_date_range(date_text, year)
        if not date_start:
            return None

        # Build event name
        name = f"Horse Boarding Championship {round_text} - {venue_text}"

        # Extract ticket link if present
        link = item.find("a", href=True)
        event_url = link["href"] if link else CHAMPIONSHIP_URL

        return self._build_event(
            name=name,
            date_start=date_start,
            date_end=date_end,
            venue_name=venue_text,
            discipline="Horse Boarding",
            url=event_url,
        )

    def _parse_date_range(
        self, text: str, year: int
    ) -> tuple[str | None, str | None]:
        """Parse date text like 'April 20th - 21st' into ISO date strings.

        Returns (date_start, date_end) where date_end is None for single-day.
        """
        # Try range without dash first: "September 13th 14th"
        m = _DATE_RANGE_NO_DASH_RE.search(text)
        if m:
            month_str, day1, day2 = m.group(1), m.group(2), m.group(3)
            start = self._make_date(month_str, day1, year)
            end = self._make_date(month_str, day2, year)
            return start, end

        # Standard pattern: "April 20th - 21st" or "September 6th"
        m = _DATE_RE.search(text)
        if not m:
            return None, None

        month_str, day1 = m.group(1), m.group(2)
        day2 = m.group(3)  # None for single-day events

        start = self._make_date(month_str, day1, year)
        end = self._make_date(month_str, day2, year) if day2 else None

        return start, end

    @staticmethod
    def _make_date(month_str: str, day: str, year: int) -> str | None:
        """Convert month name + day + year to YYYY-MM-DD."""
        try:
            dt = datetime.strptime(f"{day} {month_str[:3]} {year}", "%d %b %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None
