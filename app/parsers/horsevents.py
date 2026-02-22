from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import infer_discipline, is_future_event
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

BASE_URL = "https://horsevents.co.uk"

# Diary listing URL — dateFilter=5 gives next 30 days, counties=-1 & showType=-1 = all
DIARY_URL = f"{BASE_URL}/diary/?dateFilter=5&counties=-1&showType=-1&cmdApply=Apply+Filter"

# UK postcode regex
POSTCODE_RE = re.compile(r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}", re.IGNORECASE)

# Max concurrent detail-page fetches
_CONCURRENCY = 8


@register_parser("horsevents")
class HorsEventsParser(BaseParser):
    """Parser for horsevents.co.uk — diary listing + concurrent JSON-LD detail pages.

    Phase 1: Single diary request gets all events for next 30 days (name, date, venue, discipline).
    Phase 2: Concurrent detail page fetches for postcodes via JSON-LD.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        today = date.today()
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": "EquiCalendar/1.0"},
        ) as client:
            # Phase 1: scrape diary listing page
            event_stubs = await self._scrape_diary(client, today)
            logger.info("HorsEvents: %d events from diary listing", len(event_stubs))

            # Phase 2: concurrent detail page fetches for postcodes
            competitions = await self._enrich_all(client, event_stubs, today)

        logger.info("HorsEvents: %d competitions extracted", len(competitions))
        return competitions

    # ------------------------------------------------------------------
    # Phase 1: Diary listing
    # ------------------------------------------------------------------

    async def _scrape_diary(self, client: httpx.AsyncClient, today: date) -> list[dict]:
        """Fetch the diary listing page and extract basic event info."""
        try:
            resp = await client.get(DIARY_URL)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("HorsEvents: diary fetch failed: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        stubs: list[dict] = []
        seen_ids: set[str] = set()

        for div in soup.find_all("div", id="colwholeevent"):
            stub = self._parse_listing_item(div, today)
            if stub and stub["event_id"] not in seen_ids:
                seen_ids.add(stub["event_id"])
                stubs.append(stub)

        return stubs

    def _parse_listing_item(self, div, today: date) -> dict | None:
        """Parse a single diary listing item."""
        # Event link and name
        title_span = div.find("span", class_="titleev")
        if not title_span:
            return None
        link = title_span.find("a", href=True)
        if not link:
            return None

        href = link["href"]
        name = link.get_text(strip=True)
        if not name:
            return None

        # Extract event ID from href like /events/51820/...
        eid_match = re.search(r"/events/(\d+)", href)
        if not eid_match:
            return None
        event_id = eid_match.group(1)

        # Subtitle: "Sat 21 Feb 2026 | Venue | Discipline"
        subtitle = div.find("p", class_="subtitleev")
        date_start = None
        venue_name = "TBC"
        discipline = None

        if subtitle:
            subtitle_text = subtitle.get_text(separator="|", strip=True)
            parts = [p.strip() for p in subtitle_text.split("|")]

            # Date is the first part
            if parts:
                date_start = self._extract_date_from_text(parts[0])

            # Venue: the darkGrey span link
            venue_el = subtitle.find("span", class_="darkGrey")
            if venue_el:
                venue_name = venue_el.get_text(strip=True) or "TBC"

            # Discipline: last link in subtitle (points to /disciplines/showtype.aspx)
            disc_link = subtitle.find("a", href=re.compile(r"/disciplines/"))
            if disc_link:
                discipline = disc_link.get_text(strip=True)

        if not date_start:
            return None

        # Filter past events
        try:
            dt = date.fromisoformat(date_start)
            if dt < today:
                return None
        except ValueError:
            pass

        return {
            "event_id": event_id,
            "name": name,
            "date_start": date_start,
            "venue_name": venue_name,
            "discipline": discipline,
            "url": f"{BASE_URL}/events/?e={event_id}",
        }

    # ------------------------------------------------------------------
    # Phase 2: Concurrent detail enrichment
    # ------------------------------------------------------------------

    async def _enrich_all(
        self, client: httpx.AsyncClient, stubs: list[dict], today: date
    ) -> list[ExtractedCompetition]:
        """Fetch detail pages concurrently and build ExtractedCompetition objects."""
        sem = asyncio.Semaphore(_CONCURRENCY)

        async def enrich_one(stub: dict) -> ExtractedCompetition | None:
            async with sem:
                try:
                    return await self._enrich_from_detail(client, stub, today)
                except Exception as e:
                    logger.debug("HorsEvents: detail failed for %s: %s", stub["event_id"], e)
                    # Fall back to listing-only data
                    return self._build_from_stub(stub)

        tasks = [enrich_one(s) for s in stubs]
        results = await asyncio.gather(*tasks)
        return [c for c in results if c is not None]

    async def _enrich_from_detail(
        self, client: httpx.AsyncClient, stub: dict, today: date
    ) -> ExtractedCompetition | None:
        """Fetch a single detail page and extract JSON-LD data."""
        url = stub["url"]
        resp = await client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        json_ld = self._extract_json_ld(soup)

        if json_ld:
            name = json_ld.get("name", stub["name"]).strip()
            start_raw = json_ld.get("startDate", "")
            end_raw = json_ld.get("endDate", "")

            date_start = self._normalize_date(start_raw) or stub["date_start"]
            date_end = self._normalize_date(end_raw)

            location = json_ld.get("location", {})
            venue_name = location.get("name", "").strip() if isinstance(location, dict) else ""
            address = location.get("address", {}) if isinstance(location, dict) else {}
            postcode = address.get("postalCode", "").strip() if isinstance(address, dict) else ""
        else:
            name = stub["name"]
            date_start = stub["date_start"]
            date_end = None
            venue_name = ""
            postcode = ""

        if not name or not date_start:
            return None

        if not is_future_event(date_start, date_end):
            return None

        # Fallback postcode from page text
        if not postcode:
            page_text = soup.get_text()
            pc_match = POSTCODE_RE.search(page_text)
            if pc_match:
                postcode = pc_match.group(0).strip()

        # Pony detection
        has_pony = any(
            kw in name.lower() for kw in ["pony", "junior", "u18", "u16", "u14"]
        )

        # Discipline: prefer listing-derived, then JSON-LD infer
        discipline = stub.get("discipline") or infer_discipline(name)

        return ExtractedCompetition(
            name=name,
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name=venue_name or stub.get("venue_name", "TBC"),
            venue_postcode=postcode or None,
            discipline=discipline,
            has_pony_classes=has_pony,
            url=url,
        )

    def _build_from_stub(self, stub: dict) -> ExtractedCompetition | None:
        """Build competition from listing data when detail page fails."""
        if not stub.get("date_start") or not stub.get("name"):
            return None
        return ExtractedCompetition(
            name=stub["name"],
            date_start=stub["date_start"],
            venue_name=stub.get("venue_name", "TBC"),
            discipline=stub.get("discipline"),
            has_pony_classes=any(
                kw in stub["name"].lower() for kw in ["pony", "junior"]
            ),
            url=stub.get("url"),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_json_ld(self, soup: BeautifulSoup) -> dict | None:
        """Extract Event JSON-LD."""
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get("@type") == "Event":
                    return data
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") == "Event":
                            return item
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    def _normalize_date(self, date_str: str) -> str | None:
        """Normalize non-standard ISO dates like 2026-2-25T12:00:00+04:00."""
        if not date_str:
            return None
        date_part = date_str.split("T")[0]
        parts = date_part.split("-")
        if len(parts) == 3:
            return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
        return date_part

    def _extract_date_from_text(self, text: str) -> str | None:
        """Extract date from listing text like 'Sat 21 Feb 2026'."""
        # Try "Wed 25 Feb 2026" or "25 Feb 2026"
        match = re.search(r"(\d{1,2})\s+(\w{3,})\s+(\d{4})", text)
        if match:
            try:
                dt = datetime.strptime(
                    f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %b %Y"
                )
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
        # Try DD/MM/YYYY
        match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if match:
            return f"{match.group(3)}-{match.group(2).zfill(2)}-{match.group(1).zfill(2)}"
        return None
