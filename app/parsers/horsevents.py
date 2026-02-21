from __future__ import annotations

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

# All discipline pages to scrape for comprehensive coverage
DISCIPLINE_PAGES = [
    "/disciplines/BritishShowjumping.aspx",
    "/disciplines/UnaffiliatedShowjumping.aspx",
    "/disciplines/BritishEventing.aspx",
    "/disciplines/BritishDressage.aspx",
    "/disciplines/UnaffiliatedDressage.aspx",
    "/disciplines/OneDayEvent.aspx",
    "/disciplines/ExpressEventing.aspx",
    "/disciplines/MixedEvent.aspx",
    "/disciplines/EquitationJumping.aspx",
    "/disciplines/Showing.aspx",
    "/disciplines/AgriculturalShow.aspx",
    "/disciplines/WorkingHunter.aspx",
    "/disciplines/Schooling.aspx",
    "/disciplines/Endurance.aspx",
    "/disciplines/Gymkhana.aspx",
    "/disciplines/WorkingEquitation.aspx",
    "/disciplines/PleasureRide.aspx",
    "/disciplines/Social.aspx",
    "/disciplines/HobbyHorse.aspx",
    "/disciplines/ArenaSchoolHire.aspx",
    "/disciplines/TuitionLessons.aspx",
    "/disciplines/Camps.aspx",
    "/disciplines/HunterTrial.aspx",
]

# Map discipline page filenames to display discipline names
PAGE_TO_DISCIPLINE = {
    "BritishShowjumping": "Show Jumping",
    "UnaffiliatedShowjumping": "Show Jumping",
    "BritishEventing": "Eventing",
    "BritishDressage": "Dressage",
    "UnaffiliatedDressage": "Dressage",
    "OneDayEvent": "Eventing",
    "ExpressEventing": "Eventing",
    "MixedEvent": "Mixed",
    "EquitationJumping": "Show Jumping",
    "Showing": "Showing",
    "AgriculturalShow": "Showing",
    "WorkingHunter": "Showing",
    "Schooling": "Schooling",
    "Endurance": "Endurance",
    "Gymkhana": "Gymkhana",
    "WorkingEquitation": "Dressage",
    "PleasureRide": "Endurance",
    "HunterTrial": "Hunter Trial",
}

# UK postcode regex
POSTCODE_RE = re.compile(r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}", re.IGNORECASE)


@register_parser("horsevents")
class HorsEventsParser(BaseParser):
    """Parser for horsevents.co.uk — UK equestrian event aggregator.

    ASP.NET server-rendered pages. No pagination — all events per discipline
    load on a single page. Detail pages have JSON-LD Event structured data.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            # Discover discipline pages dynamically, fall back to static list
            discipline_paths = await self._discover_discipline_pages(client)

            # Phase 1: Scrape all discipline listing pages for event discovery
            all_event_ids: dict[str, dict] = {}  # event_id -> basic info
            for page_path in discipline_paths:
                # Derive discipline from page filename
                page_name = page_path.split("/")[-1].replace(".aspx", "")
                discipline = PAGE_TO_DISCIPLINE.get(page_name)
                try:
                    events = await self._scrape_listing(client, f"{BASE_URL}{page_path}")
                    for evt in events:
                        eid = evt.get("event_id")
                        if eid and eid not in all_event_ids:
                            evt["discipline"] = discipline
                            all_event_ids[eid] = evt
                except Exception as e:
                    logger.debug("HorsEvents: failed to scrape %s: %s", page_path, e)

            logger.info("HorsEvents: %d unique events discovered across disciplines", len(all_event_ids))

            # Phase 2: Fetch detail pages for JSON-LD enrichment
            competitions = []
            for event_id, basic in all_event_ids.items():
                try:
                    comp = await self._enrich_from_detail(client, event_id, basic)
                    if comp:
                        competitions.append(comp)
                except Exception as e:
                    logger.debug("HorsEvents: detail page failed for %s: %s", event_id, e)
                    # Fall back to basic listing data
                    comp = self._build_basic(basic)
                    if comp:
                        competitions.append(comp)

        logger.info("HorsEvents: extracted %d competitions", len(competitions))
        return competitions

    async def _discover_discipline_pages(self, client: httpx.AsyncClient) -> list[str]:
        """Dynamically discover discipline page paths from the homepage.

        Falls back to the static DISCIPLINE_PAGES list if discovery fails.
        """
        try:
            resp = await client.get(BASE_URL)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            paths: list[str] = []
            for a in soup.find_all("a", href=re.compile(r"/disciplines/\w+\.aspx", re.IGNORECASE)):
                path = a["href"]
                if not path.startswith("/"):
                    path = "/" + path
                if path not in paths:
                    paths.append(path)

            if paths:
                # Merge with static list to ensure nothing is missed
                for static_path in DISCIPLINE_PAGES:
                    if static_path not in paths:
                        paths.append(static_path)
                logger.info("HorsEvents: discovered %d discipline pages dynamically", len(paths))
                return paths
        except Exception as e:
            logger.debug("HorsEvents: discipline discovery failed, using static list: %s", e)

        return list(DISCIPLINE_PAGES)

    async def _scrape_listing(self, client: httpx.AsyncClient, url: str) -> list[dict]:
        """Scrape a discipline listing page for event info."""
        resp = await client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        events = []
        # Find all links to event detail pages
        for a in soup.find_all("a", href=re.compile(r"/events/\?e=\d+|/events/\d+")):
            href = a["href"]
            eid_match = re.search(r"(?:\?e=|/events/)(\d+)", href)
            if not eid_match:
                continue

            event_id = eid_match.group(1)
            title = a.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            # Try to find date and venue in nearby text
            parent = a.parent
            parent_text = parent.get_text(separator=" | ", strip=True) if parent else ""

            date_start = self._extract_date_from_text(parent_text)
            detail_url = href if href.startswith("http") else f"{BASE_URL}{href}"

            events.append({
                "event_id": event_id,
                "name": title,
                "date_start": date_start,
                "detail_url": detail_url,
            })

        return events

    async def _enrich_from_detail(self, client: httpx.AsyncClient, event_id: str, basic: dict) -> ExtractedCompetition | None:
        """Fetch detail page and extract JSON-LD + HTML data."""
        url = f"{BASE_URL}/events/?e={event_id}"
        resp = await client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Try JSON-LD first
        json_ld = self._extract_json_ld(soup)

        if json_ld:
            name = json_ld.get("name", basic.get("name", ""))
            start_date = json_ld.get("startDate", "")
            end_date = json_ld.get("endDate", "")

            # Normalize non-standard date format (2026-2-25T12:00:00+04:00)
            date_start = self._normalize_date(start_date)
            date_end = self._normalize_date(end_date)

            location = json_ld.get("location", {})
            venue_name = location.get("name", "") if isinstance(location, dict) else ""
            address = location.get("address", {}) if isinstance(location, dict) else {}
            postcode = address.get("postalCode", "") if isinstance(address, dict) else ""
        else:
            name = basic.get("name", "")
            date_start = basic.get("date_start")
            date_end = None
            venue_name = ""
            postcode = ""

        if not name or not date_start:
            return None

        # Filter past events
        if not is_future_event(date_start, date_end):
            return None

        # If no postcode from JSON-LD, try page text
        if not postcode:
            page_text = soup.get_text()
            pc_match = POSTCODE_RE.search(page_text)
            if pc_match:
                postcode = pc_match.group(0).strip()

        # Extract classes from detail page
        classes = self._extract_classes(soup)

        # Detect pony
        has_pony = self._detect_pony(name, classes, soup.get_text())

        # Discipline: prefer page-derived, then infer from name
        discipline = basic.get("discipline") or infer_discipline(name)

        return ExtractedCompetition(
            name=name,
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name=venue_name or basic.get("name", "TBC"),
            venue_postcode=postcode or None,
            discipline=discipline,
            has_pony_classes=has_pony,
            classes=classes,
            url=f"{BASE_URL}/events/?e={event_id}",
        )

    def _build_basic(self, basic: dict) -> ExtractedCompetition | None:
        """Build from listing data only when detail page fails."""
        if not basic.get("date_start") or not basic.get("name"):
            return None
        if not is_future_event(basic["date_start"]):
            return None
        return ExtractedCompetition(
            name=basic["name"],
            date_start=basic["date_start"],
            venue_name="TBC",
            discipline=basic.get("discipline"),
            url=basic.get("detail_url"),
        )

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
        """Normalize potentially non-standard ISO dates like 2026-2-25T12:00:00+04:00."""
        if not date_str:
            return None
        # Strip time portion
        date_part = date_str.split("T")[0]
        # Pad month/day: 2026-2-25 -> 2026-02-25
        parts = date_part.split("-")
        if len(parts) == 3:
            return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
        return date_part

    def _extract_date_from_text(self, text: str) -> str | None:
        """Extract date from listing text like 'Wed 25 Feb 2026' or '28/2/2026'."""
        # Try DD/M/YYYY or DD/MM/YYYY
        match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if match:
            return f"{match.group(3)}-{match.group(2).zfill(2)}-{match.group(1).zfill(2)}"
        # Try "Wed 25 Feb 2026"
        match = re.search(r"\w+\s+(\d{1,2})\s+(\w+)\s+(\d{4})", text)
        if match:
            try:
                dt = datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %b %Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
        return None

    def _extract_classes(self, soup: BeautifulSoup) -> list[str]:
        """Extract class names from detail page tables."""
        classes = []
        for table in soup.find_all("table"):
            for tr in table.find_all("tr"):
                tds = tr.find_all("td")
                if tds:
                    text = tds[0].get_text(strip=True)
                    if text and len(text) > 3 and not text.startswith("Event Class"):
                        classes.append(text)
        return classes

    def _detect_pony(self, name: str, classes: list[str], page_text: str) -> bool:
        text = f"{name} {' '.join(classes)}".lower()
        return any(kw in text for kw in ["pony", "junior", "u18", "u16", "u14"])
