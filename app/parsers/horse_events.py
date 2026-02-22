from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import infer_discipline
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://www.horse-events.co.uk/event/event-sitemap.xml"
BASE_URL = "https://www.horse-events.co.uk"
RALLIES_VIEWALL = f"{BASE_URL}/pony-club-rallies/?viewall=1"

# UK postcode regex
POSTCODE_RE = re.compile(r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}", re.IGNORECASE)

# YYYYMMDD suffix in event URL slugs, e.g. …-20260222/ or …-20260222-1/
_SLUG_DATE_RE = re.compile(r"(\d{4})(\d{2})(\d{2})(?:-\d+)?/?$")

# Ordinal date in listing text: "22nd February 2026", "3rd March 2026"
_LISTING_DATE_RE = re.compile(
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

# Max concurrent individual-page fetches
_CONCURRENCY = 8


def _date_from_slug(url: str) -> date | None:
    """Try to extract a date from the YYYYMMDD suffix in an event URL slug."""
    m = _SLUG_DATE_RE.search(url)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None


@register_parser("horse_events")
class HorseEventsParser(BaseParser):
    """Parser for horse-events.co.uk — bulk listing + concurrent detail fetches."""

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        today = date.today()
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": "EquiCalendar/1.0"},
        ) as client:
            # Phase 1: bulk-parse the pony-club-rallies viewall listing
            rallies, rally_urls = await self._parse_rallies_listing(client, today)
            logger.info(
                "Horse Events: %d competitions from rallies listing page", len(rallies)
            )

            # Phase 2: get /horse-events/ URLs from sitemap (rallies already covered)
            sitemap_urls = await self._get_event_urls_from_sitemap(client)
            detail_urls = [
                u for u in sitemap_urls
                if "/horse-events/" in u and self._is_future_url(u, today)
            ]
            logger.info(
                "Horse Events: %d sitemap URLs, %d to fetch after filtering",
                len(sitemap_urls),
                len(detail_urls),
            )

            detail_comps = await self._fetch_detail_pages(client, detail_urls, today)
            logger.info(
                "Horse Events: %d competitions from detail pages", len(detail_comps)
            )

            competitions = rallies + detail_comps

        logger.info("Horse Events: %d total competitions", len(competitions))
        return competitions

    # ------------------------------------------------------------------
    # Bulk rallies listing
    # ------------------------------------------------------------------

    async def _parse_rallies_listing(
        self, client: httpx.AsyncClient, today: date
    ) -> tuple[list[ExtractedCompetition], set[str]]:
        """Fetch the pony-club-rallies viewall page and parse all listings."""
        comps: list[ExtractedCompetition] = []
        urls_seen: set[str] = set()
        try:
            resp = await client.get(RALLIES_VIEWALL)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Horse Events: rallies listing fetch failed: %s", e)
            return comps, urls_seen

        soup = BeautifulSoup(resp.text, "html.parser")

        # Each listing item is a div with class search-result or event-listing-item
        items = soup.find_all("div", class_=re.compile(r"search-result|event-listing-item"))
        if not items:
            # Fallback: try finding any div with data-href (common WP event pattern)
            items = soup.find_all("div", attrs={"data-href": True})
        if not items:
            # Last resort: find all h3 siblings in the main content
            items = soup.select(".content-area h3, main h3, #content h3")

        for item in items:
            comp = self._parse_listing_item(item, today)
            if comp:
                comps.append(comp)
                urls_seen.add(comp.url)

        return comps, urls_seen

    def _parse_listing_item(
        self, item, today: date
    ) -> ExtractedCompetition | None:
        """Parse a single listing item from the viewall page."""
        # Find URL
        link = item.find("a", href=True)
        if not link:
            if item.get("data-href"):
                event_url = item["data-href"]
            else:
                return None
        else:
            event_url = link["href"]
        if not event_url.startswith("http"):
            event_url = BASE_URL + event_url

        # Find title (h3 or .result-title)
        title_el = item.find("h3") or item.find(class_="result-title")
        if not title_el:
            return None
        name = title_el.get_text(strip=True)
        if not name:
            return None

        # Find date from listing text
        item_text = item.get_text(" ", strip=True)
        start_date = None
        end_date = None

        # Try extracting dates from the text
        date_matches = list(_LISTING_DATE_RE.finditer(item_text))
        if date_matches:
            first = date_matches[0]
            try:
                start_date = date(
                    int(first.group(3)),
                    _MONTH_MAP[first.group(2).lower()],
                    int(first.group(1)),
                )
            except (ValueError, KeyError):
                pass

            if len(date_matches) >= 2:
                last = date_matches[-1]
                try:
                    end_date = date(
                        int(last.group(3)),
                        _MONTH_MAP[last.group(2).lower()],
                        int(last.group(1)),
                    )
                except (ValueError, KeyError):
                    pass

        # Fallback: try date from URL slug
        if not start_date:
            start_date = _date_from_slug(event_url)

        if not start_date:
            return None

        # Skip past events
        if start_date < today:
            return None

        # Don't return end_date if same as start
        if end_date and end_date == start_date:
            end_date = None

        # Venue from "Location: X" text
        venue_name = "TBC"
        loc_match = re.search(r"Location:\s*(.+?)(?:\s*Booking|\s*Withdrawal|\s*$)", item_text)
        if loc_match:
            venue_name = loc_match.group(1).strip()

        # Pony detection
        is_pony = (
            "/pony-club-rallies/" in event_url
            or any(kw in name.lower() for kw in ["pony", "junior", "u18", "u16", "u14"])
        )

        discipline = infer_discipline(name) or ("Pony Club" if "/pony-club-rallies/" in event_url else None)

        return ExtractedCompetition(
            name=name,
            date_start=start_date.isoformat(),
            date_end=end_date.isoformat() if end_date else None,
            venue_name=venue_name,
            venue_postcode=None,  # resolved by scanner via Venue table
            discipline=discipline,
            has_pony_classes=is_pony,
            url=event_url,
        )

    # ------------------------------------------------------------------
    # Sitemap discovery
    # ------------------------------------------------------------------

    async def _get_event_urls_from_sitemap(self, client: httpx.AsyncClient) -> list[str]:
        """Fetch the event sitemap XML and extract all event URLs."""
        try:
            resp = await client.get(SITEMAP_URL)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Horse Events: sitemap fetch failed: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "xml")
        urls = []
        for loc in soup.find_all("loc"):
            url = loc.get_text(strip=True)
            if "/horse-events/" in url or "/pony-club-rallies/" in url:
                urls.append(url)
        return urls

    def _is_future_url(self, url: str, today: date) -> bool:
        """Check if a URL's embedded date is in the future (or undetermined)."""
        d = _date_from_slug(url)
        if d is None:
            return True  # can't tell, include it
        return d >= today

    # ------------------------------------------------------------------
    # Concurrent detail page fetches
    # ------------------------------------------------------------------

    async def _fetch_detail_pages(
        self, client: httpx.AsyncClient, urls: list[str], today: date
    ) -> list[ExtractedCompetition]:
        """Fetch individual event pages concurrently."""
        sem = asyncio.Semaphore(_CONCURRENCY)
        results: list[ExtractedCompetition | None] = []

        async def fetch_one(url: str) -> ExtractedCompetition | None:
            async with sem:
                try:
                    return await self._parse_event_page(client, url, today)
                except Exception as e:
                    logger.debug("Horse Events: failed to parse %s: %s", url, e)
                    return None

        tasks = [fetch_one(u) for u in urls]
        results = await asyncio.gather(*tasks)
        return [c for c in results if c is not None]

    async def _parse_event_page(
        self, client: httpx.AsyncClient, url: str, today: date
    ) -> ExtractedCompetition | None:
        """Parse a single event page using JSON-LD + JS variables."""
        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        # Extract JSON-LD Event data
        json_ld = self._extract_json_ld(soup)
        if not json_ld:
            return None

        name = json_ld.get("name", "").strip()
        start_date_str = json_ld.get("startDate", "")
        end_date_str = json_ld.get("endDate", "")

        if not name or not start_date_str:
            return None

        # Filter past events
        try:
            start_dt = date.fromisoformat(start_date_str)
            if start_dt < today:
                return None
        except ValueError:
            pass

        # Venue from JSON-LD
        location = json_ld.get("location", {})
        venue_name = location.get("name", "").strip() if isinstance(location, dict) else ""

        # Postcode from JS variable or page text
        postcode = self._extract_postcode(html, soup)

        # Pony detection
        is_pony = (
            "/pony-club-rallies/" in url
            or any(kw in name.lower() for kw in ["pony", "junior", "u18", "u16", "u14"])
        )

        discipline = infer_discipline(name) or ("Pony Club" if "/pony-club-rallies/" in url else None)

        end_date = end_date_str if end_date_str and end_date_str != start_date_str else None

        return ExtractedCompetition(
            name=name,
            date_start=start_date_str,
            date_end=end_date,
            venue_name=venue_name or "TBC",
            venue_postcode=postcode,
            discipline=discipline,
            has_pony_classes=is_pony,
            url=url,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_json_ld(self, soup: BeautifulSoup) -> dict | None:
        """Extract Event JSON-LD from the page."""
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if data.get("@type") == "Event":
                        return data
                    graph = data.get("@graph", [])
                    for item in graph:
                        if item.get("@type") == "Event":
                            return item
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") == "Event":
                            return item
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    def _extract_postcode(self, html: str, soup: BeautifulSoup) -> str | None:
        """Extract venue postcode from JS variable or page text."""
        # Try JS variable first (fast)
        m = re.search(r"var\s+event_postcode\s*=\s*['\"]([^'\"]+)['\"]", html)
        if m:
            return m.group(1).strip()
        # Fallback: first UK postcode in page text
        page_text = soup.get_text()
        m = POSTCODE_RE.search(page_text)
        return m.group(0).strip() if m else None
