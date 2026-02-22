from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import (
    detect_pony_classes,
    extract_postcode,
    infer_discipline,
    is_future_event,
)
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.equoevents.co.uk/SearchEvents"
VENUE_URL = "https://www.equoevents.co.uk/Venues/View/{id}"
BASE_URL = "https://www.equoevents.co.uk"

# Date format on listing: "Sat 21 Feb 2026"
DATE_FMT = "%a %d %b %Y"


@register_parser("equo_events")
class EquoEventsParser(BaseParser):
    """Parser for equoevents.co.uk — server-rendered ASP.NET MVC.

    Paginates through /SearchEvents?Page=N and extracts events from the
    HTML table. Venue detail pages provide postcodes and coordinates.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        limits = httpx.Limits(max_connections=15, max_keepalive_connections=10)
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=30.0, limits=limits
        ) as client:
            # Phase 1: Discover total pages and scrape all listing pages
            all_events = await self._scrape_all_pages(client)
            logger.info("EquoEvents: %d raw events from listing pages", len(all_events))

            # Phase 2: Enrich with venue postcodes/coordinates
            venue_cache: dict[str, str | None] = {}
            sem = asyncio.Semaphore(10)

            async def _lookup_venue(event: dict) -> None:
                vid = event.get("venue_id")
                if not vid:
                    return
                if vid not in venue_cache:
                    async with sem:
                        try:
                            venue_cache[vid] = await self._fetch_venue_postcode(
                                client, vid
                            )
                        except Exception as e:
                            logger.debug(
                                "EquoEvents: venue %s fetch failed: %s", vid, e
                            )
                            venue_cache[vid] = None
                event["venue_postcode"] = venue_cache.get(vid)

            # Collect unique venue IDs first to minimise requests
            unique_venue_ids = {e.get("venue_id") for e in all_events if e.get("venue_id")}
            logger.info("EquoEvents: fetching %d unique venues for postcodes", len(unique_venue_ids))

            for vid in unique_venue_ids:
                async with sem:
                    try:
                        venue_cache[vid] = await self._fetch_venue_postcode(client, vid)
                    except Exception as e:
                        logger.debug("EquoEvents: venue %s fetch failed: %s", vid, e)
                        venue_cache[vid] = None
                await asyncio.sleep(0.1)

            # Phase 3: Build ExtractedCompetition objects
            competitions: list[ExtractedCompetition] = []
            seen: set[int] = set()

            for event in all_events:
                eid = event.get("event_id")
                if eid and eid in seen:
                    continue
                if eid:
                    seen.add(eid)

                comp = self._to_competition(event, venue_cache)
                if comp:
                    competitions.append(comp)

        logger.info("EquoEvents: extracted %d competitions", len(competitions))
        return competitions

    async def _scrape_all_pages(self, client: httpx.AsyncClient) -> list[dict]:
        """Fetch page 1 to get total pages, then scrape all pages."""
        resp = await client.get(SEARCH_URL, params={"Sort": "StartDate", "Desc": "False"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        total_pages = self._get_total_pages(soup)
        logger.info("EquoEvents: %d pages to scrape", total_pages)

        events = self._parse_listing_page(soup)

        for page in range(2, total_pages + 1):
            try:
                resp = await client.get(
                    SEARCH_URL,
                    params={"Page": page, "Sort": "StartDate", "Desc": "False"},
                )
                resp.raise_for_status()
                page_soup = BeautifulSoup(resp.text, "html.parser")
                page_events = self._parse_listing_page(page_soup)
                events.extend(page_events)
                logger.debug("EquoEvents: page %d — %d events", page, len(page_events))
            except Exception as e:
                logger.warning("EquoEvents: failed to fetch page %d: %s", page, e)

            await asyncio.sleep(0.2)

        return events

    def _get_total_pages(self, soup: BeautifulSoup) -> int:
        """Extract total pages from hidden pager input."""
        pager = soup.find("input", id=re.compile(r"_pager\.TotalPages$", re.IGNORECASE))
        if pager and pager.get("value"):
            try:
                return int(pager["value"])
            except ValueError:
                pass
        # Fallback: look for any hidden input with TotalPages in name
        for inp in soup.find_all("input", type="hidden"):
            name = inp.get("name", "") + inp.get("id", "")
            if "TotalPages" in name:
                try:
                    return int(inp.get("value", "1"))
                except ValueError:
                    pass
        return 1

    def _parse_listing_page(self, soup: BeautifulSoup) -> list[dict]:
        """Parse events from a search results page."""
        events: list[dict] = []

        # Each event is in a div.tr.with-buttons-pseudo-row
        for row in soup.find_all("div", class_="tr"):
            if "tr-head" in row.get("class", []):
                continue

            # Skip the buttons pseudo-row — we extract event_id from it separately
            if "buttons-pseudo-row" in row.get("class", []):
                continue

            event: dict = {}

            # Date: first span with text-bold
            date_span = row.find("span", class_="text-bold")
            if date_span:
                event["date_text"] = date_span.get_text(strip=True)

            # Event name and URL from link to ViewEventDetails
            event_link = row.find("a", href=re.compile(r"/ViewEvent/ViewEventDetails/\d+"))
            if event_link:
                event["name"] = event_link.get_text(strip=True)
                href = event_link["href"]
                event["url"] = BASE_URL + href if not href.startswith("http") else href
                # Extract event ID from URL
                m = re.search(r"/ViewEventDetails/(\d+)", href)
                if m:
                    event["event_id"] = int(m.group(1))

            # Discipline
            disc_span = row.find("span", attrs={"data-title": "Discipline"})
            if disc_span:
                event["discipline_text"] = disc_span.get_text(strip=True)

            # Venue name and ID
            venue_link = row.find("a", href=re.compile(r"/Venues/View/\d+"))
            if venue_link:
                event["venue_name"] = venue_link.get_text(strip=True)
                vm = re.search(r"/Venues/View/(\d+)", venue_link["href"])
                if vm:
                    event["venue_id"] = vm.group(1)

            # Location/city
            loc_span = row.find("span", attrs={"data-title": "Location"})
            if loc_span:
                event["location"] = loc_span.get_text(strip=True)

            # Only add if we have at least a name
            if event.get("name"):
                events.append(event)

        return events

    async def _fetch_venue_postcode(self, client: httpx.AsyncClient, venue_id: str) -> str | None:
        """Fetch a venue detail page and extract the postcode."""
        resp = await client.get(VENUE_URL.format(id=venue_id))
        resp.raise_for_status()
        return extract_postcode(resp.text)

    def _to_competition(self, event: dict, venue_cache: dict[str, str | None]) -> ExtractedCompetition | None:
        """Convert a raw event dict to an ExtractedCompetition."""
        name = event.get("name", "").strip()
        if not name:
            return None

        # Parse date
        date_text = event.get("date_text", "")
        date_start = self._parse_date(date_text)
        if not date_start:
            return None

        if not is_future_event(date_start):
            return None

        venue_name = event.get("venue_name", "TBC")
        venue_id = event.get("venue_id")
        venue_postcode = venue_cache.get(venue_id) if venue_id else None

        # Discipline
        disc_text = event.get("discipline_text", "")
        text = f"{name} {disc_text}"
        discipline = infer_discipline(text) or disc_text or None
        has_pony = detect_pony_classes(text)

        return ExtractedCompetition(
            name=name,
            date_start=date_start,
            date_end=None,
            venue_name=venue_name,
            venue_postcode=venue_postcode,
            discipline=discipline,
            has_pony_classes=has_pony,
            classes=[],
            url=event.get("url") or SEARCH_URL,
        )

    def _parse_date(self, text: str) -> str | None:
        """Parse 'Sat 21 Feb 2026' to 'YYYY-MM-DD'."""
        if not text:
            return None
        try:
            return datetime.strptime(text.strip(), DATE_FMT).strftime("%Y-%m-%d")
        except ValueError:
            # Try without day-of-week
            try:
                return datetime.strptime(text.strip(), "%d %b %Y").strftime("%Y-%m-%d")
            except ValueError:
                logger.debug("EquoEvents: unparseable date '%s'", text)
                return None
