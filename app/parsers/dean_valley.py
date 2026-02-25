from __future__ import annotations

import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.parsers.bases import BROWSER_UA, SingleVenueParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, infer_discipline
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

# Parse dates from ai1ec event titles: "Wednesday 4th March", "18th April"
_DATE_NO_YEAR_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)",
    re.IGNORECASE,
)

_URL_DATE_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?-"
    r"(january|february|march|april|may|june|july|august|september|october|november|december)",
    re.IGNORECASE,
)
_URL_NUMERIC_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")


@register_parser("dean_valley")
class DeanValleyParser(SingleVenueParser):
    """Parser for deanvalley.co.uk — Timely ai1ec plugin, HTML scraping.

    Fetches the /events/ agenda view with ai1ec-event containers.
    Single venue: Dean Valley Equestrian (SK7 1RQ).
    """

    VENUE_NAME = "Dean Valley"
    VENUE_POSTCODE = "SK7 1RQ"
    BASE_URL = "https://www.deanvalley.co.uk"
    HEADERS = {"User-Agent": BROWSER_UA}

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        competitions: list[ExtractedEvent] = []

        async with self._make_client() as client:
            events_url = f"{self.BASE_URL}/events/"
            for page_offset in range(4):
                fetch_url = events_url if page_offset == 0 else \
                    f"{events_url}action~agenda/page_offset~{page_offset}/"

                try:
                    resp = await client.get(fetch_url)
                    resp.raise_for_status()
                except httpx.HTTPError:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                found = self._extract_events(soup)
                if not found:
                    break

                for title, date_start, event_url in found:
                    competitions.append(self._build_event(
                        name=title,
                        date_start=date_start,
                        discipline=infer_discipline(title),
                        has_pony_classes=detect_pony_classes(title),
                        url=event_url,
                    ))

        competitions = self._dedup(competitions)
        self._log_result("Dean Valley", len(competitions))
        return competitions

    def _extract_events(self, soup):
        results = []
        now = datetime.now()

        for event_div in soup.select(".ai1ec-event"):
            title_el = event_div.select_one(".ai1ec-event-title")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            event_url = ""
            for link in event_div.select("a[href*='/event/']"):
                href = link.get("href", "")
                if href:
                    event_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
                    break

            date_start = self._extract_date_from_text(title, now)
            if not date_start and event_url:
                date_start = self._extract_date_from_url(event_url, now)
            if not date_start:
                container_text = event_div.get_text(separator=" ", strip=True)
                date_start = self._extract_date_from_text(container_text, now)

            if date_start and event_url:
                results.append((title, date_start, event_url))

        return results

    def _extract_date_from_text(self, text, now):
        m = _DATE_NO_YEAR_RE.search(text)
        if m:
            try:
                dt = datetime.strptime(f"{int(m.group(1))} {m.group(2)} {now.year}", "%d %B %Y")
                if dt.month < now.month or (dt.month == now.month and dt.day < now.day):
                    dt = dt.replace(year=now.year + 1)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
        return None

    def _extract_date_from_url(self, url, now):
        m = _URL_NUMERIC_DATE_RE.search(url)
        if m:
            day, month, year = m.groups()
            try:
                return datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
            except ValueError:
                pass

        m = _URL_DATE_RE.search(url)
        if m:
            day_str, month_str = m.groups()
            day = re.sub(r"(st|nd|rd|th)$", "", day_str)
            try:
                dt = datetime.strptime(f"{int(day)} {month_str} {now.year}", "%d %B %Y")
                if dt.month < now.month or (dt.month == now.month and dt.day < now.day):
                    dt = dt.replace(year=now.year + 1)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

        return None
