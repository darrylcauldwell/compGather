from __future__ import annotations

import html
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.parsers.bases import BROWSER_UA, SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

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
_MULTI_RANGE_RE = re.compile(
    r"(\d{1,2})\s*[-–]\s*\d{1,2}\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s*(?:&amp;|&)\s*"
    r"\d{1,2}\s*[-–]\s*(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})"
)


@register_parser("hickstead")
class HicksteadParser(SingleVenueParser):
    """Parser for hickstead.co.uk — Umbraco CMS, HTML scraping.

    Single venue: All England Jumping Course, Hickstead (BN6 9NS).
    """

    VENUE_NAME = "Hickstead"
    VENUE_POSTCODE = "BN6 9NS"
    BASE_URL = "https://www.hickstead.co.uk"
    HEADERS = {"User-Agent": BROWSER_UA}

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        async with self._make_client() as client:
            soup = await self._fetch_html(client, url)

            show_urls = self._extract_show_urls(soup)
            if not show_urls:
                logger.warning("Hickstead: no show URLs found on listing page")
                return []

            first_url = f"{self.BASE_URL}{show_urls[0]}"
            text = await self._fetch_text(client, first_url)

            competitions = self._parse_detail_page(text, show_urls[0])

        self._log_result("Hickstead", len(competitions))
        return competitions

    def _extract_show_urls(self, soup: BeautifulSoup):
        urls, seen = [], set()
        for link in soup.select("a[href^='/horse-shows-tickets/horse-shows/the-']"):
            href = link.get("href", "")
            if href and href not in seen:
                seen.add(href)
                urls.append(href)
        return urls

    def _parse_detail_page(self, page_html, main_show_path):
        competitions = []
        soup = BeautifulSoup(page_html, "html.parser")

        main_date_div = soup.select_one("div.uk-text-center.uk-text-italic.font-georgia.font20")
        if main_date_div:
            date_text = main_date_div.get_text(separator=" ", strip=True)
            heading = soup.select_one("h1, h2.font-georgia")
            title = heading.get_text(strip=True) if heading else self._slug_to_title(main_show_path)

            comp = self._make_competition(
                html.unescape(title), date_text, f"{self.BASE_URL}{main_show_path}"
            )
            if comp:
                competitions.append(comp)

        for card in soup.select("div.padding16all"):
            date_div = card.select_one("div.tk-museo-sans-rounded, div.weight500")
            if not date_div:
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

            if href.rstrip("/") == main_show_path.rstrip("/"):
                continue

            event_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
            comp = self._make_competition(title, date_text, event_url)
            if comp:
                competitions.append(comp)

        return competitions

    def _make_competition(self, title, date_text, event_url):
        date_start, date_end = self._parse_dates(date_text)
        if not date_start:
            return None

        return self._build_event(
            name=title,
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            discipline="Show Jumping",
            url=event_url,
        )

    def _parse_dates(self, text):
        text = html.unescape(text)

        m = _MULTI_RANGE_RE.search(text)
        if m:
            first_day, first_month, last_day, last_month, year = m.groups()
            try:
                start = datetime.strptime(f"{int(first_day)} {first_month} {year}", "%d %B %Y")
                end = datetime.strptime(f"{int(last_day)} {last_month} {year}", "%d %B %Y")
                return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
            except ValueError:
                pass

        m = _DATE_RANGE_RE.search(text)
        if m:
            start_day, end_day, month, year = m.groups()
            try:
                start = datetime.strptime(f"{int(start_day)} {month} {year}", "%d %B %Y")
                end = datetime.strptime(f"{int(end_day)} {month} {year}", "%d %B %Y")
                return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
            except ValueError:
                pass

        m = _SINGLE_DATE_RE.search(text)
        if m:
            day, month, year = m.groups()
            try:
                dt = datetime.strptime(f"{int(day)} {month} {year}", "%d %B %Y")
                return dt.strftime("%Y-%m-%d"), None
            except ValueError:
                pass

        return None, None

    def _slug_to_title(self, path):
        slug = path.rstrip("/").split("/")[-1]
        return slug.replace("-", " ").title()
