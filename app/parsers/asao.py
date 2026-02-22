from __future__ import annotations

import asyncio
import logging
import re
from datetime import date

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import extract_postcode, is_future_event
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

BASE_URL = "https://www.asao.co.uk"

# Search Filter Pro AJAX endpoint for upcoming events (form id 4898)
LISTING_URL = f"{BASE_URL}/"

# Ordinal date patterns: "2nd April 2026", "13th-16th May 2026", "9-12 July 2024"
_SINGLE_DATE_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{4})",
    re.IGNORECASE,
)

# Range: "13th-16th May 2026" or "9-12 July 2024" or "28th June - 1st July 2026"
_RANGE_DATE_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s*[-–]\s*(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{4})",
    re.IGNORECASE,
)

# Cross-month range: "28th June - 1st July 2026"
_CROSS_MONTH_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s*[-–]\s*"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{4})",
    re.IGNORECASE,
)

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

_CONCURRENCY = 8


@register_parser("asao")
class ASAOParser(BaseParser):
    """Parser for ASAO (Association of Show & Agricultural Organisations).

    Phase 1: Paginate through Search Filter Pro AJAX listing (8 events/page).
    Phase 2: Fetch detail pages concurrently for venue, postcode, and coordinates.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        today = date.today()
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": "EquiCalendar/1.0"},
        ) as client:
            # Phase 1: discover events from paginated listing
            stubs = await self._scrape_listing(client)
            logger.info("ASAO: %d events from listing pages", len(stubs))

            # Phase 2: fetch detail pages concurrently
            competitions = await self._enrich_all(client, stubs, today)

        logger.info("ASAO: %d competitions extracted", len(competitions))
        return competitions

    # ------------------------------------------------------------------
    # Phase 1: Listing pages
    # ------------------------------------------------------------------

    async def _scrape_listing(self, client: httpx.AsyncClient) -> list[dict]:
        """Paginate through the Search Filter Pro AJAX endpoint."""
        stubs: list[dict] = []
        seen_urls: set[str] = set()

        for page in range(1, 20):  # safety limit
            try:
                resp = await client.get(
                    LISTING_URL,
                    params={
                        "sfid": "4898",
                        "sf_action": "get_data",
                        "sf_data": "results",
                        "sf_paged": str(page),
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                html = data.get("results", "")
                if not html or not html.strip():
                    break
            except Exception as e:
                logger.debug("ASAO: listing page %d failed: %s", page, e)
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

    def _parse_listing_item(self, item) -> dict | None:
        """Parse a listing card for basic event info."""
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

        # Date from p.startDate
        date_el = item.find("p", class_="startDate")
        date_text = date_el.get_text(strip=True) if date_el else ""

        # Region from p.region
        region_el = item.find("p", class_="region")
        region = region_el.get_text(strip=True) if region_el else ""

        return {
            "name": name,
            "url": url,
            "date_text": date_text,
            "region": region,
        }

    # ------------------------------------------------------------------
    # Phase 2: Detail page enrichment
    # ------------------------------------------------------------------

    async def _enrich_all(
        self, client: httpx.AsyncClient, stubs: list[dict], today: date
    ) -> list[ExtractedCompetition]:
        """Fetch detail pages concurrently."""
        sem = asyncio.Semaphore(_CONCURRENCY)

        async def enrich_one(stub: dict) -> ExtractedCompetition | None:
            async with sem:
                try:
                    return await self._parse_detail(client, stub, today)
                except Exception as e:
                    logger.debug("ASAO: detail failed for %s: %s", stub["url"], e)
                    return self._build_from_stub(stub, today)

        tasks = [enrich_one(s) for s in stubs]
        results = await asyncio.gather(*tasks)
        return [c for c in results if c is not None]

    async def _parse_detail(
        self, client: httpx.AsyncClient, stub: dict, today: date
    ) -> ExtractedCompetition | None:
        """Parse an event detail page."""
        resp = await client.get(stub["url"])
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Name from h1
        h1 = soup.find("h1")
        name = h1.get_text(strip=True) if h1 else stub["name"]

        # Date from p.bigDate or listing fallback
        date_el = soup.find("p", class_="bigDate")
        date_text = date_el.get_text(strip=True) if date_el else stub["date_text"]
        date_start, date_end = self._parse_date_text(date_text)

        if not date_start:
            # Try listing date as fallback
            date_start, date_end = self._parse_date_text(stub["date_text"])

        if not date_start:
            return None
        if not is_future_event(date_start, date_end):
            return None

        # Address/postcode from p.address
        venue_name = "TBC"
        venue_postcode = None
        addr_el = soup.find("p", class_="address")
        if addr_el:
            addr_text = addr_el.get_text(strip=True)
            venue_postcode = extract_postcode(addr_text)
            # Use the address text as venue hint (strip postcode and ", UK")
            clean_addr = re.sub(r",?\s*UK\s*$", "", addr_text, flags=re.IGNORECASE)
            if venue_postcode:
                idx = clean_addr.upper().find(venue_postcode.upper())
                if idx > 0:
                    clean_addr = clean_addr[:idx].rstrip(" ,.-")
            if clean_addr and len(clean_addr) > 2:
                venue_name = clean_addr

        # Lat/lng from div.marker
        latitude = None
        longitude = None
        marker = soup.find("div", class_="marker")
        if marker:
            try:
                lat_str = marker.get("data-lat", "")
                lng_str = marker.get("data-lng", "")
                if lat_str and lng_str:
                    latitude = float(lat_str)
                    longitude = float(lng_str)
            except (ValueError, TypeError):
                pass

        # Website URL
        website = None
        web_link = soup.find("a", class_="visitWeb")
        if web_link:
            website = web_link.get("href")

        return ExtractedCompetition(
            name=name,
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name=venue_name,
            venue_postcode=venue_postcode,
            latitude=latitude,
            longitude=longitude,
            discipline="Agricultural Show",
            has_pony_classes=False,
            url=website or stub["url"],
        )

    def _build_from_stub(self, stub: dict, today: date) -> ExtractedCompetition | None:
        """Fallback: build from listing data when detail page fails."""
        date_start, date_end = self._parse_date_text(stub["date_text"])
        if not date_start:
            return None
        if not is_future_event(date_start, date_end):
            return None

        return ExtractedCompetition(
            name=stub["name"],
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name="TBC",
            discipline="Agricultural Show",
            has_pony_classes=False,
            url=stub["url"],
        )

    # ------------------------------------------------------------------
    # Date parsing
    # ------------------------------------------------------------------

    def _parse_date_text(self, text: str) -> tuple[str | None, str | None]:
        """Parse various date formats from ASAO listings."""
        if not text:
            return None, None

        # Try cross-month range first: "28th June - 1st July 2026"
        m = _CROSS_MONTH_RE.search(text)
        if m:
            start = self._build_date(m.group(1), m.group(2), m.group(5))
            end = self._build_date(m.group(3), m.group(4), m.group(5))
            return start, end

        # Try same-month range: "13th-16th May 2026" or "9-12 July 2024"
        m = _RANGE_DATE_RE.search(text)
        if m:
            start = self._build_date(m.group(1), m.group(3), m.group(4))
            end = self._build_date(m.group(2), m.group(3), m.group(4))
            return start, end

        # Try single date: "2nd April 2026"
        m = _SINGLE_DATE_RE.search(text)
        if m:
            start = self._build_date(m.group(1), m.group(2), m.group(3))
            return start, None

        return None, None

    def _build_date(self, day: str, month_name: str, year: str) -> str | None:
        """Build ISO date from components."""
        try:
            m = _MONTH_MAP[month_name.lower()]
            d = int(day)
            y = int(year)
            return date(y, m, d).isoformat()
        except (KeyError, ValueError):
            return None
