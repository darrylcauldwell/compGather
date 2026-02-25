from __future__ import annotations

import logging
import re
from datetime import date

from bs4 import BeautifulSoup

from app.parsers.bases import TwoPhaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import extract_postcode
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

BASE_URL = "https://www.asao.co.uk"
LISTING_URL = f"{BASE_URL}/"

_SINGLE_DATE_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{4})", re.IGNORECASE,
)
_RANGE_DATE_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s*[-–]\s*(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{4})", re.IGNORECASE,
)
_CROSS_MONTH_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s*[-–]\s*(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{4})", re.IGNORECASE,
)
_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


@register_parser("asao")
class ASAOParser(TwoPhaseParser):
    """Parser for ASAO (Association of Show & Agricultural Organisations).

    Phase 1: Paginate through Search Filter Pro AJAX listing.
    Phase 2: Fetch detail pages concurrently for venue, postcode, coordinates.
    """

    CONCURRENCY = 8

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        async with self._make_client() as client:
            stubs = await self._scrape_listing(client)
            logger.info("ASAO: %d events from listing pages", len(stubs))

            competitions = await self._concurrent_fetch(
                stubs,
                lambda stub: self._parse_detail(client, stub),
                fallback_fn=self._build_from_stub,
            )

        self._log_result("ASAO", len(competitions))
        return competitions

    async def _scrape_listing(self, client):
        stubs, seen_urls = [], set()
        for page in range(1, 20):
            try:
                data = await self._fetch_json(
                    client, LISTING_URL,
                    params={"sfid": "4898", "sf_action": "get_data", "sf_data": "results", "sf_paged": str(page)},
                )
                html = data.get("results", "")
                if not html or not html.strip():
                    break
            except Exception:
                break

            soup = BeautifulSoup(html, "html.parser")
            items = soup.find_all("div", class_="event-item")
            if not items:
                break

            for item in items:
                stub = self._parse_listing_item(item)
                if stub and stub["url"] not in seen_urls:
                    seen_urls.add(stub["url"])
                    stubs.append(stub)
        return stubs

    def _parse_listing_item(self, item):
        h2 = item.find("h2")
        if not h2:
            return None
        link = h2.find("a", href=True)
        if not link:
            return None

        name = link.get_text(strip=True)
        url = link["href"]
        if not name or not url:
            return None

        date_el = item.find("p", class_="startDate")
        region_el = item.find("p", class_="region")

        return {
            "name": name, "url": url,
            "date_text": date_el.get_text(strip=True) if date_el else "",
            "region": region_el.get_text(strip=True) if region_el else "",
        }

    async def _parse_detail(self, client, stub):
        soup = await self._fetch_html(client, stub["url"])

        h1 = soup.find("h1")
        name = h1.get_text(strip=True) if h1 else stub["name"]

        date_el = soup.find("p", class_="bigDate")
        date_text = date_el.get_text(strip=True) if date_el else stub["date_text"]
        date_start, date_end = self._parse_date_text(date_text)
        if not date_start:
            date_start, date_end = self._parse_date_text(stub["date_text"])
        if not date_start:
            return None

        venue_name, venue_postcode = "TBC", None
        addr_el = soup.find("p", class_="address")
        if addr_el:
            addr_text = addr_el.get_text(strip=True)
            venue_postcode = extract_postcode(addr_text)
            clean_addr = re.sub(r",?\s*UK\s*$", "", addr_text, flags=re.IGNORECASE)
            if venue_postcode:
                idx = clean_addr.upper().find(venue_postcode.upper())
                if idx > 0:
                    clean_addr = clean_addr[:idx].rstrip(" ,.-")
            if clean_addr and len(clean_addr) > 2:
                venue_name = clean_addr

        latitude, longitude = None, None
        marker = soup.find("div", class_="marker")
        if marker:
            try:
                lat_str, lng_str = marker.get("data-lat", ""), marker.get("data-lng", "")
                if lat_str and lng_str:
                    latitude, longitude = float(lat_str), float(lng_str)
            except (ValueError, TypeError):
                pass

        website = None
        web_link = soup.find("a", class_="visitWeb")
        if web_link:
            website = web_link.get("href")

        return self._build_event(
            name=name, date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name=venue_name, venue_postcode=venue_postcode,
            latitude=latitude, longitude=longitude,
            discipline="Agricultural Show", has_pony_classes=False,
            url=website or stub["url"],
        )

    def _build_from_stub(self, stub):
        date_start, date_end = self._parse_date_text(stub["date_text"])
        if not date_start:
            return None
        return self._build_event(
            name=stub["name"], date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name="TBC", discipline="Agricultural Show",
            has_pony_classes=False, url=stub["url"],
        )

    def _parse_date_text(self, text):
        if not text:
            return None, None

        m = _CROSS_MONTH_RE.search(text)
        if m:
            start = self._build_date(m.group(1), m.group(2), m.group(5))
            end = self._build_date(m.group(3), m.group(4), m.group(5))
            return start, end

        m = _RANGE_DATE_RE.search(text)
        if m:
            start = self._build_date(m.group(1), m.group(3), m.group(4))
            end = self._build_date(m.group(2), m.group(3), m.group(4))
            return start, end

        m = _SINGLE_DATE_RE.search(text)
        if m:
            return self._build_date(m.group(1), m.group(2), m.group(3)), None

        return None, None

    def _build_date(self, day, month_name, year):
        try:
            m = _MONTH_MAP[month_name.lower()]
            return date(int(year), m, int(day)).isoformat()
        except (KeyError, ValueError):
            return None
