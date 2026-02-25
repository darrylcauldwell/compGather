from __future__ import annotations

import logging
import re
from datetime import date, datetime

import httpx
from bs4 import BeautifulSoup

from app.parsers.bases import BROWSER_UA, SingleVenueParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, infer_discipline
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


@register_parser("northallerton")
class NorthallertonParser(SingleVenueParser):
    """Parser for northallertonequestriancentre.co.uk — Classic ASP, monthly diary.

    Single venue: Northallerton Equestrian Centre (DL7 0PQ).
    """

    VENUE_NAME = "Northallerton"
    VENUE_POSTCODE = "DL7 0PQ"
    BASE_URL = "https://www.northallertonequestriancentre.co.uk"
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

                try:
                    soup = await self._fetch_html(
                        client,
                        f"{self.BASE_URL}/diary/default.asp",
                        params={"mth": month},
                    )
                except httpx.HTTPError:
                    continue

                for title, date_start, event_url in self._extract_events(soup, year, month):
                    competitions.append(self._build_event(
                        name=title,
                        date_start=date_start,
                        discipline=infer_discipline(title),
                        has_pony_classes=detect_pony_classes(title),
                        url=event_url,
                    ))

        competitions = self._dedup(competitions)
        self._log_result("Northallerton", len(competitions))
        return competitions

    def _extract_events(self, soup: BeautifulSoup, default_year: int, month: int):
        results = []
        for tr in soup.select("table tr"):
            cells = tr.select("td")
            if len(cells) < 2:
                continue

            date_text = cells[0].get_text(strip=True)
            m = _DATE_RE.search(date_text)
            if not m:
                continue

            day, month_s, year = m.groups()
            try:
                date_start = datetime(int(year), int(month_s), int(day)).strftime("%Y-%m-%d")
            except ValueError:
                continue

            title = cells[1].get_text(strip=True)
            if not title or len(title) < 3 or "CANCELLED" in title.upper():
                continue

            link = cells[1].select_one("a[href]")
            if link:
                href = link.get("href", "")
                event_url = href if href.startswith("http") else f"{self.BASE_URL}/diary/{href}"
            else:
                event_url = f"{self.BASE_URL}/diary/default.asp?mth={month}"

            results.append((title, date_start, event_url))
        return results
