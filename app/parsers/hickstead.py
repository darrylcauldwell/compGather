from __future__ import annotations

import html
import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, is_future_event
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

BASE_URL = "https://www.hickstead.co.uk"
VENUE_NAME = "Hickstead"
VENUE_POSTCODE = "BN6 9NS"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# Date patterns: "18 - 21 June 2026", "Friday 26 June 2026",
# "02 – 6 September & 09 - 13 September 2026"
_DATE_RANGE_RE = re.compile(
    r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})"
)
_SINGLE_DATE_RE = re.compile(
    r"(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})"
)
# Multi-part: "02 – 6 September & 09 - 13 September 2026"
_MULTI_RANGE_RE = re.compile(
    r"(\d{1,2})\s*[-–]\s*\d{1,2}\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s*(?:&amp;|&)\s*"
    r"\d{1,2}\s*[-–]\s*(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})"
)


@register_parser("hickstead")
class HicksteadParser(BaseParser):
    """Parser for hickstead.co.uk — Umbraco CMS, HTML scraping.

    Single venue: All England Jumping Course, Hickstead (BN6 9NS).
    Fetches the first show detail page which has a sidebar listing
    all upcoming shows with dates.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=30.0, headers=HEADERS
        ) as client:
            # Fetch the listing page to get show URLs
            resp = await client.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            show_urls = self._extract_show_urls(soup)
            if not show_urls:
                logger.warning("Hickstead: no show URLs found on listing page")
                return []

            # Fetch the first show's detail page — its sidebar lists all shows with dates
            first_url = f"{BASE_URL}{show_urls[0]}"
            resp = await client.get(first_url)
            resp.raise_for_status()

            competitions = self._parse_detail_page(resp.text, show_urls[0])

        logger.info("Hickstead: extracted %d competitions", len(competitions))
        return competitions

    def _extract_show_urls(self, soup: BeautifulSoup) -> list[str]:
        """Extract unique show detail page URLs from the listing page."""
        urls: list[str] = []
        seen: set[str] = set()
        for link in soup.select("a[href^='/horse-shows-tickets/horse-shows/the-']"):
            href = link.get("href", "")
            if href and href not in seen:
                seen.add(href)
                urls.append(href)
        return urls

    def _parse_detail_page(self, page_html: str, main_show_path: str) -> list[ExtractedCompetition]:
        """Extract all shows from a detail page (main show + sidebar shows)."""
        competitions: list[ExtractedCompetition] = []
        soup = BeautifulSoup(page_html, "html.parser")

        # 1. Main show: date in the header area
        main_date_div = soup.select_one("div.uk-text-center.uk-text-italic.font-georgia.font20")
        if main_date_div:
            date_text = main_date_div.get_text(separator=" ", strip=True)
            # Title from the page heading
            heading = soup.select_one("h1, h2.font-georgia")
            title = heading.get_text(strip=True) if heading else None
            if not title:
                title = self._slug_to_title(main_show_path)

            comp = self._make_competition(
                html.unescape(title), date_text,
                f"{BASE_URL}{main_show_path}",
            )
            if comp:
                competitions.append(comp)

        # 2. Sidebar shows: padding16all divs with date + title link
        for card in soup.select("div.padding16all"):
            date_div = card.select_one("div.tk-museo-sans-rounded, div.weight500")
            if not date_div:
                # Try the first div child
                date_div = card.find("div")
            if not date_div:
                continue

            date_text = date_div.get_text(separator=" ", strip=True)
            if not re.search(r"\d{4}", date_text):
                continue

            link = card.select_one("a[href*='horse-shows-tickets/horse-shows/']")
            if not link:
                continue

            title = html.unescape(link.get_text(strip=True))
            href = link.get("href", "")
            if not title or not href:
                continue

            # Skip if same as main show (already added)
            if href.rstrip("/") == main_show_path.rstrip("/"):
                continue

            event_url = f"{BASE_URL}{href}" if href.startswith("/") else href
            comp = self._make_competition(title, date_text, event_url)
            if comp:
                competitions.append(comp)

        return competitions

    def _make_competition(
        self, title: str, date_text: str, event_url: str
    ) -> ExtractedCompetition | None:
        """Parse date text and build an ExtractedCompetition."""
        date_start, date_end = self._parse_dates(date_text)
        if not date_start:
            return None

        if not is_future_event(date_start, date_end):
            return None

        has_pony = detect_pony_classes(title)

        return ExtractedCompetition(
            name=title,
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name=VENUE_NAME,
            venue_postcode=VENUE_POSTCODE,
            discipline="Show Jumping",
            has_pony_classes=has_pony,
            classes=[],
            url=event_url,
        )

    def _parse_dates(self, text: str) -> tuple[str | None, str | None]:
        """Parse date range text into (date_start, date_end) ISO strings.

        Handles:
          "18 - 21 June 2026"
          "Friday 26 June 2026"
          "02 – 6 September & 09 - 13 September 2026"
        """
        # Normalise HTML entities
        text = html.unescape(text)

        # Multi-part range: "02 – 6 September & 09 - 13 September 2026"
        m = _MULTI_RANGE_RE.search(text)
        if m:
            first_day, first_month, last_day, last_month, year = m.groups()
            try:
                start = datetime.strptime(f"{int(first_day)} {first_month} {year}", "%d %B %Y")
                end = datetime.strptime(f"{int(last_day)} {last_month} {year}", "%d %B %Y")
                return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Simple range: "18 - 21 June 2026"
        m = _DATE_RANGE_RE.search(text)
        if m:
            start_day, end_day, month, year = m.groups()
            try:
                start = datetime.strptime(f"{int(start_day)} {month} {year}", "%d %B %Y")
                end = datetime.strptime(f"{int(end_day)} {month} {year}", "%d %B %Y")
                return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Single date: "Friday 26 June 2026" or "26 June 2026"
        m = _SINGLE_DATE_RE.search(text)
        if m:
            day, month, year = m.groups()
            try:
                dt = datetime.strptime(f"{int(day)} {month} {year}", "%d %B %Y")
                return dt.strftime("%Y-%m-%d"), None
            except ValueError:
                pass

        return None, None

    def _slug_to_title(self, path: str) -> str:
        """Convert URL slug to a readable title as fallback."""
        slug = path.rstrip("/").split("/")[-1]
        return slug.replace("-", " ").title()
