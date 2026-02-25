from __future__ import annotations

import logging
import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from app.parsers.bases import BROWSER_UA, SingleVenueParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, infer_discipline
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("brook_farm")
class BrookFarmParser(SingleVenueParser):
    """Parser for brookfarmtc.co.uk — custom PHP calendar, HTML scraping.

    Fetches monthly calendar pages at /what-s-on-2.php.
    Single venue: Brook Farm Training Centre (RM4 1EJ).
    """

    VENUE_NAME = "Brook Farm (RM4)"
    VENUE_POSTCODE = "RM4 1EJ"
    BASE_URL = "https://www.brookfarmtc.co.uk"
    HEADERS = {"User-Agent": BROWSER_UA}

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        competitions: list[ExtractedEvent] = []
        today = date.today()

        async with self._make_client() as client:
            for offset in range(6):
                month = today.month + offset
                year = today.year
                while month > 12:
                    month -= 12
                    year += 1

                soup = await self._fetch_html(
                    client,
                    f"{self.BASE_URL}/what-s-on-2.php",
                    params={"cntnt01year": year, "cntnt01month": month},
                )

                for title, date_start, event_url in self._extract_events(soup, year, month):
                    competitions.append(self._build_event(
                        name=title,
                        date_start=date_start,
                        discipline=infer_discipline(title),
                        has_pony_classes=detect_pony_classes(title),
                        url=event_url,
                    ))

        competitions = self._dedup(competitions)
        self._log_result("Brook Farm", len(competitions))
        return competitions

    def _extract_events(self, soup: BeautifulSoup, year: int, month: int):
        results = []
        for link in soup.select("a[href*='/calendar/80/']"):
            href = link.get("href", "")
            title = link.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            td = link.find_parent("td")
            day = None
            if td:
                day_text = td.get_text(separator="\n", strip=True).split("\n")[0]
                m = re.match(r"(\d{1,2})", day_text)
                if m:
                    day = int(m.group(1))

            if not day:
                continue
            try:
                date_start = datetime(year, month, day).strftime("%Y-%m-%d")
            except ValueError:
                continue

            event_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
            results.append((title, date_start, event_url))
        return results
