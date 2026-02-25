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


@register_parser("sykehouse")
class SykehouseParser(SingleVenueParser):
    """Parser for sykehousearena.com — Events Manager plugin, HTML scraping.

    Fetches /events/ calendar pages for current and next 5 months.
    Single venue: Sykehouse Arena (DN14 9AX).
    """

    VENUE_NAME = "Sykehouse Arena"
    VENUE_POSTCODE = "DN14 9AX"
    BASE_URL = "https://www.sykehousearena.com"
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
                    f"{self.BASE_URL}/events/",
                    params={"mo": month, "yr": year},
                )

                event_links: list[str] = []
                for link in soup.select("a[href*='/events/']"):
                    href = link.get("href", "")
                    if not href or href.rstrip("/") == f"{self.BASE_URL}/events" or "?" in href:
                        continue
                    if "/events/" in href and href != f"{self.BASE_URL}/events/":
                        full = href if href.startswith("http") else f"{self.BASE_URL}{href}"
                        if full not in event_links:
                            event_links.append(full)

                for event_url in event_links:
                    try:
                        resp = await client.get(event_url)
                        resp.raise_for_status()
                    except httpx.HTTPError:
                        continue

                    comp = self._parse_event_page(resp.text, event_url)
                    if comp:
                        competitions.append(comp)

        competitions = self._dedup(competitions)
        self._log_result("Sykehouse", len(competitions))
        return competitions

    def _parse_event_page(self, html_text, event_url):
        soup = BeautifulSoup(html_text, "html.parser")

        title_el = soup.select_one(".entry-title, h1.post-title, h1")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        if not title:
            return None

        page_text = soup.get_text(separator=" ", strip=True)

        date_start = None
        time_el = soup.select_one("time[datetime]")
        if time_el:
            dt_str = time_el.get("datetime", "")
            if dt_str and len(dt_str) >= 10:
                date_start = dt_str[:10]

        if not date_start:
            m = re.search(
                r"(\d{1,2})\s+(January|February|March|April|May|June|July|"
                r"August|September|October|November|December)\s+(\d{4})",
                page_text, re.IGNORECASE,
            )
            if m:
                try:
                    dt = datetime.strptime(f"{int(m.group(1))} {m.group(2)} {m.group(3)}", "%d %B %Y")
                    date_start = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass

        if not date_start:
            m = re.search(
                r"(January|February|March|April|May|June|July|"
                r"August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
                page_text, re.IGNORECASE,
            )
            if m:
                try:
                    dt = datetime.strptime(f"{int(m.group(2))} {m.group(1)} {m.group(3)}", "%d %B %Y")
                    date_start = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass

        if not date_start:
            return None

        return self._build_event(
            name=title,
            date_start=date_start,
            discipline=infer_discipline(title),
            has_pony_classes=detect_pony_classes(title),
            url=event_url,
        )
