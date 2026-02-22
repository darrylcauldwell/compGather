from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime

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

CALENDAR_URL = "https://bsha.online/index.php"

# Ordinal date regex: "Sunday 8th Mar 2026"
_DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)\s+(\w+)\s+(\d{4})",
    re.IGNORECASE,
)

# Domains where we can reliably find venue data
_VENUE_DOMAINS = ("lite.events", "entrymaster.online", "showingscene.com")

# Max concurrent venue lookups
_CONCURRENCY = 6


@register_parser("bsha")
class BSHAParser(BaseParser):
    """Parser for BSHA (British Show Horse Association) show calendar.

    Phase 1: Fetches 12 monthly calendar pages from bsha.online.
    Phase 2: Fetches entry/website links concurrently to enrich venue + postcode.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        today = date.today()
        stubs: list[dict] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": "EquiCalendar/1.0"},
        ) as client:
            # Phase 1: scrape all 12 monthly calendar pages
            for month in range(1, 13):
                try:
                    month_stubs = await self._scrape_month(client, month, today)
                    for stub in month_stubs:
                        key = f"{stub['name']}|{stub['date_start']}"
                        if key not in seen:
                            seen.add(key)
                            stubs.append(stub)
                except Exception as e:
                    logger.debug("BSHA: failed to scrape month %d: %s", month, e)

            logger.info("BSHA: %d shows from calendar, enriching venues...", len(stubs))

            # Phase 2: enrich venue data from entry/website links
            competitions = await self._enrich_venues(client, stubs)

        logger.info("BSHA: %d competitions extracted", len(competitions))
        return competitions

    # ------------------------------------------------------------------
    # Phase 1: Calendar scraping
    # ------------------------------------------------------------------

    async def _scrape_month(
        self, client: httpx.AsyncClient, month: int, today: date
    ) -> list[dict]:
        """Scrape a single month's calendar page into stub dicts."""
        resp = await client.get(CALENDAR_URL, params={"id": "74", "month": str(month)})
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        stubs: list[dict] = []

        for card in soup.find_all("div", class_=re.compile(r"\bcard-4\b")):
            stub = self._parse_card(card, today)
            if stub:
                stubs.append(stub)

        return stubs

    def _parse_card(self, card, today: date) -> dict | None:
        """Parse a single BSHA show card into a stub dict."""
        # Show name from h4 > b
        h4 = card.find("h4")
        if not h4:
            return None
        b = h4.find("b")
        name = (b.get_text(strip=True) if b else h4.get_text(strip=True))
        if not name:
            return None

        # Date from div.smallfont
        date_el = card.find("div", class_="smallfont")
        if not date_el:
            return None
        date_text = date_el.get_text(strip=True)
        date_start, date_end = self._parse_date_text(date_text)

        if not date_start:
            return None
        if not is_future_event(date_start, date_end):
            return None

        # Venue: BSHA cards rarely include venue — check showattr divs
        venue_name = "TBC"
        venue_postcode = None
        for attr_div in card.find_all("div", class_="showattr"):
            strong = attr_div.find("strong")
            if strong and "Venue" in strong.get_text():
                venue_text = attr_div.get_text(strip=True)
                venue_text = re.sub(r"^Venue:\s*", "", venue_text)
                if venue_text.strip():
                    venue_name = venue_text.strip()
                    venue_postcode = extract_postcode(venue_name)
                break

        # Collect ALL entry/website links for venue enrichment
        links: list[str] = []
        event_url = None
        for a in card.find_all("a", class_="nodecor"):
            href = a.get("href", "")
            if not href or not href.startswith("http"):
                continue
            href = href.replace("\\", "/")
            link_text = a.get_text(strip=True)
            if "Entries" in link_text or "Website" in link_text:
                links.append(href)
                if not event_url:
                    event_url = href

        return {
            "name": name,
            "date_start": date_start,
            "date_end": date_end if date_end and date_end != date_start else None,
            "venue_name": venue_name,
            "venue_postcode": venue_postcode,
            "links": links,
            "event_url": event_url,
        }

    # ------------------------------------------------------------------
    # Phase 2: Venue enrichment from entry/website links
    # ------------------------------------------------------------------

    async def _enrich_venues(
        self, client: httpx.AsyncClient, stubs: list[dict]
    ) -> list[ExtractedCompetition]:
        """Fetch entry/website links concurrently to find venue data."""
        sem = asyncio.Semaphore(_CONCURRENCY)

        async def enrich_one(stub: dict) -> ExtractedCompetition:
            # Only try enrichment if we don't already have venue data
            if stub["venue_name"] == "TBC" and stub["links"]:
                async with sem:
                    venue, postcode = await self._try_venue_from_links(
                        client, stub["links"]
                    )
                    if venue:
                        stub["venue_name"] = venue
                    if postcode:
                        stub["venue_postcode"] = postcode
            return self._stub_to_comp(stub)

        tasks = [enrich_one(s) for s in stubs]
        return list(await asyncio.gather(*tasks))

    async def _try_venue_from_links(
        self, client: httpx.AsyncClient, links: list[str]
    ) -> tuple[str | None, str | None]:
        """Try each link to extract venue + postcode. Returns first success."""
        for link in links:
            try:
                resp = await client.get(link, timeout=15.0)
                if resp.status_code != 200:
                    continue
                html = resp.text
                soup = BeautifulSoup(html, "html.parser")

                venue, postcode = self._extract_venue_from_page(soup, html)
                if venue or postcode:
                    return venue, postcode
            except Exception as e:
                logger.debug("BSHA: venue fetch failed for %s: %s", link, e)
        return None, None

    def _extract_venue_from_page(
        self, soup: BeautifulSoup, html: str
    ) -> tuple[str | None, str | None]:
        """Extract venue name and postcode from an entry/website page."""
        page_text = soup.get_text(" ", strip=True)
        venue = None
        postcode = None

        # Boundary pattern: stops at field labels, not content words
        _FIELD_BOUNDARY = (
            r"(?:\n|\r|Entry Fee|Entries Close|Entries Open|Contact:|Organis|Secretary|"
            r"Phone:|E-mail:|Email:|Judge|Class\b|Date:)"
        )

        # Strategy 1: Look for "Venue:" labelled text (lite.events, entrymaster.online)
        venue_match = re.search(
            r"Venue:\s*(.+?)" + _FIELD_BOUNDARY,
            page_text,
            re.IGNORECASE,
        )
        if venue_match:
            venue_text = venue_match.group(1).strip().rstrip(".")
            postcode = extract_postcode(venue_text)
            # Clean venue: take everything before the postcode
            if postcode:
                idx = venue_text.upper().index(postcode.upper())
                venue = venue_text[:idx].rstrip(" ,.-")
            else:
                venue = venue_text
            if venue:
                return venue, postcode

        # Strategy 2: Look for "Location:" labelled text (showingscene.com)
        loc_match = re.search(
            r"Location:\s*(.+?)" + _FIELD_BOUNDARY,
            page_text,
            re.IGNORECASE,
        )
        if loc_match:
            loc_text = loc_match.group(1).strip().rstrip(".")
            postcode = extract_postcode(loc_text)
            if postcode:
                idx = loc_text.upper().index(postcode.upper())
                venue = loc_text[:idx].rstrip(" ,.-")
            else:
                venue = loc_text
            if venue:
                return venue, postcode

        # Strategy 3: Look for "Address:" labelled text
        addr_match = re.search(
            r"Address:\s*(.+?)" + _FIELD_BOUNDARY,
            page_text,
            re.IGNORECASE,
        )
        if addr_match:
            addr_text = addr_match.group(1).strip()
            postcode = extract_postcode(addr_text)
            if postcode:
                return None, postcode

        # Strategy 4: Just find any postcode on the page (fallback for show websites)
        postcode = extract_postcode(page_text)
        if postcode:
            return None, postcode

        return None, None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _stub_to_comp(self, stub: dict) -> ExtractedCompetition:
        """Convert a stub dict to an ExtractedCompetition."""
        return ExtractedCompetition(
            name=stub["name"],
            date_start=stub["date_start"],
            date_end=stub["date_end"],
            venue_name=stub["venue_name"],
            venue_postcode=stub["venue_postcode"],
            discipline=infer_discipline(stub["name"]) or "Showing",
            has_pony_classes=detect_pony_classes(stub["name"]),
            url=stub["event_url"] or CALENDAR_URL,
        )

    def _parse_date_text(self, text: str) -> tuple[str | None, str | None]:
        """Parse date text, handling ranges with ' - ' separator."""
        matches = list(_DATE_RE.finditer(text))
        if not matches:
            return None, None

        date_start = self._match_to_iso(matches[0])
        date_end = self._match_to_iso(matches[-1]) if len(matches) > 1 else None

        return date_start, date_end

    def _match_to_iso(self, m: re.Match) -> str | None:
        """Convert regex match to ISO date string."""
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %b %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None
