from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.parsers.bases import BROWSER_UA, SingleVenueParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, infer_discipline
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r",?\s*(\d{4})",
    re.IGNORECASE,
)


@register_parser("solihull")
class SolihullParser(SingleVenueParser):
    """Parser for solihullridingclub.co.uk — JetEngine calendar, HTML scraping.

    Single venue: Solihull Riding Club (B93 8QE).
    """

    VENUE_NAME = "Solihull"
    VENUE_POSTCODE = "B93 8QE"
    BASE_URL = "https://solihullridingclub.co.uk"
    HEADERS = {"User-Agent": BROWSER_UA}

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        competitions: list[ExtractedEvent] = []

        async with self._make_client() as client:
            soup = await self._fetch_html(client, f"{self.BASE_URL}/event-diary/")

            event_urls: list[str] = []
            for link in soup.select("a[href*='/event/']"):
                href = link.get("href", "")
                if href and "/event/" in href:
                    full_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
                    if full_url not in event_urls:
                        event_urls.append(full_url)

            logger.info("Solihull: found %d event links", len(event_urls))

            for event_url in event_urls:
                try:
                    resp = await client.get(event_url)
                    resp.raise_for_status()
                except Exception:
                    continue

                comp = self._parse_event_page(resp.text, event_url)
                if comp:
                    competitions.append(comp)

        competitions = self._dedup(competitions)
        self._log_result("Solihull", len(competitions))
        return competitions

    def _parse_event_page(self, html_text, event_url):
        soup = BeautifulSoup(html_text, "html.parser")

        h1 = soup.select_one("h1")
        if not h1:
            return None
        title = h1.get_text(strip=True)
        if not title:
            return None

        page_text = soup.get_text(separator=" ", strip=True)
        m = _DATE_RE.search(page_text)
        if not m:
            return None

        day, month, year = m.groups()
        try:
            dt = datetime.strptime(f"{int(day)} {month} {year}", "%d %B %Y")
        except ValueError:
            return None

        return self._build_event(
            name=title,
            date_start=dt.strftime("%Y-%m-%d"),
            discipline=infer_discipline(title),
            has_pony_classes=detect_pony_classes(title),
            url=event_url,
        )
