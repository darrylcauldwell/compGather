from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.parsers.bases import BROWSER_UA, SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

EVENTS_URL = "https://www.hartpury.ac.uk/equine/events/"
MAX_PAGES = 10

_DATE_RE = re.compile(
    r"(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)",
    re.IGNORECASE,
)


@register_parser("hartpury")
class HartpuryParser(SingleVenueParser):
    """Parser for hartpury.ac.uk — Umbraco CMS, HTML scraping.

    Fetches paginated equine events listing (9 per page).
    Single venue: Hartpury University (GL19 3BE).
    """

    VENUE_NAME = "Hartpury"
    VENUE_POSTCODE = "GL19 3BE"
    BASE_URL = "https://www.hartpury.ac.uk"
    HEADERS = {"User-Agent": BROWSER_UA}

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        competitions: list[ExtractedEvent] = []

        async with self._make_client() as client:
            for page in range(1, MAX_PAGES + 1):
                soup = await self._fetch_html(client, EVENTS_URL, params={"page": page})
                cards = self._extract_cards(soup)
                if not cards:
                    break

                for title, date_start, event_url in cards:
                    competitions.append(self._build_event(
                        name=title,
                        date_start=date_start,
                        discipline=None,
                        url=event_url,
                    ))

                if len(cards) < 9:
                    break

        competitions = self._dedup(competitions)
        self._log_result("Hartpury", len(competitions))
        return competitions

    def _extract_cards(self, soup: BeautifulSoup):
        results = []
        now = datetime.now()

        for link in soup.select("a[href*='/equine/events/']"):
            href = link.get("href", "")
            if href in (EVENTS_URL, "/equine/events/", "/equine/events"):
                continue

            heading = link.select_one("h3, h2, h4")
            title = heading.get_text(strip=True) if heading else link.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            date_text = ""
            parent = link.parent
            if parent:
                date_text = parent.get_text(separator=" ", strip=True)

            m = _DATE_RE.search(date_text)
            if not m:
                m = _DATE_RE.search(link.get_text(separator=" ", strip=True))
            if not m:
                continue

            day, month = m.groups()
            try:
                dt = datetime.strptime(f"{int(day)} {month} {now.year}", "%d %B %Y")
                if dt.month < now.month or (dt.month == now.month and dt.day < now.day):
                    dt = dt.replace(year=now.year + 1)
            except ValueError:
                continue

            event_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
            results.append((title, dt.strftime("%Y-%m-%d"), event_url))

        return results
