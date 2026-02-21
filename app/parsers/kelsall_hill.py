from __future__ import annotations

import asyncio
import logging
import re

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import (
    detect_pony_classes,
    extract_json_ld_event,
    infer_discipline,
    is_competition_event,
    is_future_event,
)
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

BASE_URL = "https://kelsallhill.co.uk"
EVENTS_URL = f"{BASE_URL}/events/"
SITEMAP_URL = f"{BASE_URL}/wp-sitemap-posts-mec-events-1.xml"
VENUE_NAME = "Kelsall Hill"
VENUE_POSTCODE = "CW6 0PE"

# Max concurrent detail page fetches
CONCURRENCY_LIMIT = 10


@register_parser("kelsall_hill")
class KelsallHillParser(BaseParser):
    """Parser for kelsallhill.co.uk — WordPress with Modern Events Calendar.

    Primary discovery via MEC events sitemap for complete coverage.
    Falls back to listing page scrape if sitemap is unavailable.
    Filters out non-competition events (clinics, workshops, etc.).
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            # Phase 1: Discover event URLs (sitemap first, listing fallback)
            event_urls = await self._get_event_urls_from_sitemap(client)
            if not event_urls:
                event_urls = await self._get_event_urls_from_listing(client)
            logger.info("Kelsall Hill: found %d event URLs", len(event_urls))

            # Phase 2: Fetch detail pages with concurrency limit
            semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
            tasks = [self._parse_event_with_semaphore(semaphore, client, eu) for eu in event_urls]
            results = await asyncio.gather(*tasks)

            competitions = [comp for comp in results if comp is not None]

        logger.info("Kelsall Hill: extracted %d competitions", len(competitions))
        return competitions

    async def _get_event_urls_from_sitemap(self, client: httpx.AsyncClient) -> list[str]:
        """Parse MEC events sitemap XML for all event URLs."""
        try:
            resp = await client.get(SITEMAP_URL)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.debug("Kelsall Hill: sitemap fetch failed: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "xml")
        urls = []
        for loc in soup.find_all("loc"):
            url = loc.get_text(strip=True)
            if "/events/" in url and url != EVENTS_URL:
                urls.append(url)

        logger.info("Kelsall Hill: %d URLs from sitemap", len(urls))
        return urls

    async def _get_event_urls_from_listing(self, client: httpx.AsyncClient) -> list[str]:
        """Fallback: scrape the /events/ listing page for event detail URLs."""
        urls: list[str] = []
        try:
            resp = await client.get(EVENTS_URL)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Kelsall Hill: listing page fetch failed: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # MEC event articles contain links to detail pages
        for article in soup.find_all("div", class_="mec-event-article"):
            link = article.find("a", href=True)
            if link:
                href = link["href"]
                if "/events/" in href and href != EVENTS_URL:
                    full_url = href if href.startswith("http") else BASE_URL + href
                    if full_url not in urls:
                        urls.append(full_url)

        # Also look for any other event links in the page
        for link in soup.find_all("a", href=re.compile(r"/events/[^/]+/")):
            href = link["href"]
            full_url = href if href.startswith("http") else BASE_URL + href
            if full_url not in urls and full_url != EVENTS_URL:
                urls.append(full_url)

        return urls

    async def _parse_event_with_semaphore(
        self, semaphore: asyncio.Semaphore, client: httpx.AsyncClient, url: str
    ) -> ExtractedCompetition | None:
        """Wrapper to limit concurrency on detail page fetches."""
        async with semaphore:
            try:
                return await self._parse_event_page(client, url)
            except Exception as e:
                logger.warning("Kelsall Hill: failed to parse %s: %s", url, e)
                return None

    async def _parse_event_page(self, client: httpx.AsyncClient, url: str) -> ExtractedCompetition | None:
        """Parse a single event detail page using JSON-LD + HTML description."""
        resp = await client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract JSON-LD structured data
        json_ld = extract_json_ld_event(soup)
        if not json_ld:
            logger.debug("Kelsall Hill: no JSON-LD found on %s", url)
            return None

        name = json_ld.get("name", "").strip()
        start_date = json_ld.get("startDate", "")
        end_date = json_ld.get("endDate", "")

        if not name or not start_date:
            return None

        # Filter past events
        if not is_future_event(start_date, end_date):
            return None

        # Filter non-competition events (clinics, workshops, etc.)
        if not is_competition_event(name):
            logger.debug("Kelsall Hill: skipping non-competition '%s'", name)
            return None

        # Parse description HTML for additional fields
        description = json_ld.get("description", "")
        page_text = soup.get_text()

        classes = self._extract_classes(description, page_text)
        has_pony = detect_pony_classes(f"{name} {description} {' '.join(classes)}")
        discipline = infer_discipline(f"{name} {description}")

        return ExtractedCompetition(
            name=name,
            date_start=start_date,
            date_end=end_date if end_date and end_date != start_date else None,
            venue_name=VENUE_NAME,
            venue_postcode=VENUE_POSTCODE,
            discipline=discipline,
            has_pony_classes=has_pony,
            classes=classes,
            url=url,
        )

    def _extract_classes(self, description: str, page_text: str) -> list[str]:
        """Extract class heights/names from description text."""
        classes = []
        # Look for "Classes: 70cm | 80cm | 90cm | 1.00m" pattern
        match = re.search(r"(?:Classes?|Heights?)\s*[:\-]\s*(.+?)(?:\n|$)", description, re.IGNORECASE)
        if match:
            raw = match.group(1)
            classes = [c.strip() for c in re.split(r"[|,/]", raw) if c.strip()]

        if not classes:
            match = re.search(r"(?:Classes?|Heights?)\s*[:\-]\s*(.+?)(?:\n|$)", page_text, re.IGNORECASE)
            if match:
                raw = match.group(1)
                classes = [c.strip() for c in re.split(r"[|,/]", raw) if c.strip()]

        return classes
