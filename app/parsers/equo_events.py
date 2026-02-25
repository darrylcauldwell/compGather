from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx

from app.parsers.bases import TwoPhaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, extract_postcode
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.equoevents.co.uk/SearchEvents"
VENUE_URL = "https://www.equoevents.co.uk/Venues/View/{id}"
BASE_URL = "https://www.equoevents.co.uk"
DATE_FMT = "%a %d %b %Y"


@register_parser("equo_events")
class EquoEventsParser(TwoPhaseParser):
    """Parser for equoevents.co.uk — server-rendered ASP.NET MVC.

    Paginates through /SearchEvents and enriches with venue postcodes.
    """

    CONCURRENCY = 10

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        limits = httpx.Limits(max_connections=15, max_keepalive_connections=10)
        async with self._make_client(limits=limits) as client:
            all_events = await self._scrape_all_pages(client)
            logger.info("EquoEvents: %d raw events from listing pages", len(all_events))

            # Fetch unique venue postcodes
            venue_cache: dict[str, str | None] = {}
            unique_vids = {e.get("venue_id") for e in all_events if e.get("venue_id")}
            logger.info("EquoEvents: fetching %d unique venues for postcodes", len(unique_vids))

            sem = asyncio.Semaphore(self.CONCURRENCY)
            for vid in unique_vids:
                async with sem:
                    try:
                        venue_cache[vid] = await self._fetch_venue_postcode(client, vid)
                    except Exception as e:
                        logger.debug("EquoEvents: venue %s fetch failed: %s", vid, e)
                        venue_cache[vid] = None
                await asyncio.sleep(0.1)

            competitions: list[ExtractedEvent] = []
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

        self._log_result("EquoEvents", len(competitions))
        return competitions

    async def _scrape_all_pages(self, client):
        soup = await self._fetch_html(client, SEARCH_URL, params={"Sort": "StartDate", "Desc": "False"})
        total_pages = self._get_total_pages(soup)
        logger.info("EquoEvents: %d pages to scrape", total_pages)

        events = self._parse_listing_page(soup)
        for page in range(2, total_pages + 1):
            try:
                page_soup = await self._fetch_html(
                    client, SEARCH_URL,
                    params={"Page": page, "Sort": "StartDate", "Desc": "False"},
                )
                events.extend(self._parse_listing_page(page_soup))
            except Exception as e:
                logger.warning("EquoEvents: failed to fetch page %d: %s", page, e)
            await asyncio.sleep(0.2)
        return events

    def _get_total_pages(self, soup):
        pager = soup.find("input", id=re.compile(r"_pager\.TotalPages$", re.IGNORECASE))
        if pager and pager.get("value"):
            try:
                return int(pager["value"])
            except ValueError:
                pass
        for inp in soup.find_all("input", type="hidden"):
            name = inp.get("name", "") + inp.get("id", "")
            if "TotalPages" in name:
                try:
                    return int(inp.get("value", "1"))
                except ValueError:
                    pass
        return 1

    def _parse_listing_page(self, soup):
        events = []
        for row in soup.find_all("div", class_="tr"):
            if "tr-head" in row.get("class", []) or "buttons-pseudo-row" in row.get("class", []):
                continue

            event = {}
            date_span = row.find("span", class_="text-bold")
            if date_span:
                event["date_text"] = date_span.get_text(strip=True)

            event_link = row.find("a", href=re.compile(r"/ViewEvent/ViewEventDetails/\d+"))
            if event_link:
                event["name"] = event_link.get_text(strip=True)
                href = event_link["href"]
                event["url"] = BASE_URL + href if not href.startswith("http") else href
                m = re.search(r"/ViewEventDetails/(\d+)", href)
                if m:
                    event["event_id"] = int(m.group(1))

            disc_span = row.find("span", attrs={"data-title": "Discipline"})
            if disc_span:
                event["discipline_text"] = disc_span.get_text(strip=True)

            venue_link = row.find("a", href=re.compile(r"/Venues/View/\d+"))
            if venue_link:
                event["venue_name"] = venue_link.get_text(strip=True)
                vm = re.search(r"/Venues/View/(\d+)", venue_link["href"])
                if vm:
                    event["venue_id"] = vm.group(1)

            if event.get("name"):
                events.append(event)
        return events

    async def _fetch_venue_postcode(self, client, venue_id):
        resp = await client.get(VENUE_URL.format(id=venue_id))
        resp.raise_for_status()
        return extract_postcode(resp.text)

    def _to_competition(self, event, venue_cache):
        name = event.get("name", "").strip()
        if not name:
            return None

        date_text = event.get("date_text", "")
        date_start = self._parse_date_str(date_text)
        if not date_start:
            return None

        disc_text = event.get("discipline_text", "")
        venue_id = event.get("venue_id")

        return self._build_event(
            name=name, date_start=date_start,
            venue_name=event.get("venue_name", "TBC"),
            venue_postcode=venue_cache.get(venue_id) if venue_id else None,
            discipline=disc_text or None,
            has_pony_classes=detect_pony_classes(f"{name} {disc_text}"),
            url=event.get("url") or SEARCH_URL,
        )

    def _parse_date_str(self, text):
        if not text:
            return None
        for fmt in [DATE_FMT, "%d %b %Y"]:
            try:
                return datetime.strptime(text.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None
