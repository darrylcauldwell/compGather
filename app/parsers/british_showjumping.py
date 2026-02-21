from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import is_future_event
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

BASE_URL = "https://www.britishshowjumping.co.uk"
CALENDAR_URL = f"{BASE_URL}/show-calendar.cfm"
MEMBERS_URL = "https://members.britishshowjumping.co.uk"

# UK postcode regex
POSTCODE_RE = re.compile(r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}", re.IGNORECASE)

# Category code meanings for pony detection
PONY_CATEGORIES = {"J", "P"}  # Junior, Pony

# Lat/lng from Google Maps URL
LATLNG_RE = re.compile(r"maps/@([\d.-]+),([\d.-]+)")


@register_parser("british_showjumping")
class BritishShowjumpingParser(BaseParser):
    """Parser for britishshowjumping.co.uk show calendar.

    Research findings:
    - showMultiDay=0 returns ALL shows (single + multi-day) — no need for separate queries
    - Unfiltered (blank category) returns all categories — no need to query per category
    - ~20 results per page, ~100 pages for 12-month range (~2000 shows)
    - Pagination ends when NEXT link disappears (stale single-entry bug beyond last page)
    - Detail pages have: postcode, lat/lng from Google Maps, schedule tables with 9 columns
    - Members portal has: full address, secretary contact, entry deadline, cancellation status
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        today = date.today()
        date_from = today.strftime("%d/%m/%Y")
        # 12-month range to capture everything published
        date_to = (today + timedelta(days=365)).strftime("%d/%m/%Y")

        limits = httpx.Limits(max_connections=20, max_keepalive_connections=15)
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0, limits=limits) as client:
            # Phase 1: Paginate through ALL calendar listing pages
            shows = await self._fetch_all_pages(client, date_from, date_to)
            logger.info("British Showjumping: %d show-days from %d calendar pages",
                        len(shows), (len(shows) // 20) + 1)

            # Deduplicate multi-day shows (same venue on consecutive days)
            deduplicated = self._deduplicate_multiday(shows)
            logger.info("British Showjumping: %d unique shows after dedup", len(deduplicated))

            # Filter out past events (for multi-day: keep if end date >= today)
            future_shows = []
            for show in deduplicated:
                date_start = show.get("date_start_override", show["date_text"])
                date_end = show.get("date_end_override")
                if is_future_event(date_start, date_end):
                    future_shows.append(show)
            logger.info("British Showjumping: %d future shows after date filter", len(future_shows))

            # Phase 2: Fetch detail pages concurrently (semaphore-limited)
            sem = asyncio.Semaphore(15)

            async def _enrich_one(show: dict) -> ExtractedCompetition | None:
                async with sem:
                    try:
                        return await self._enrich_from_detail(client, show)
                    except Exception as e:
                        logger.warning("BS: failed to enrich %s: %s", show.get("detail_url"), e)
                        return self._build_basic_competition(show)

            results = await asyncio.gather(*[_enrich_one(s) for s in future_shows])
            competitions = [c for c in results if c is not None]

        logger.info("British Showjumping: extracted %d competitions", len(competitions))
        return competitions

    async def _fetch_all_pages(self, client: httpx.AsyncClient, date_from: str, date_to: str) -> list[dict]:
        """Fetch ALL paginated calendar pages. ~100+ pages for a 12-month range."""
        all_shows = []
        page = 1
        max_pages = 200  # Safety limit (~4000 shows)
        stop_reason = "max_pages_reached"

        while page <= max_pages:
            params = {
                "showFrom": date_from,
                "showTo": date_to,
                "showMultiDay": "0",
                "PageNum_rsEvents": str(page),
            }
            try:
                resp = await client.get(CALENDAR_URL, params=params)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning("BS: page %d fetch failed: %s", page, e)
                stop_reason = "fetch_error"
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            shows_on_page = self._parse_calendar_table(soup, date_from)

            # Detect end-of-pagination: no results, or stale single-entry bug
            if not shows_on_page:
                stop_reason = "empty_page"
                break
            if len(shows_on_page) == 1 and len(all_shows) > 0:
                # Stale entry bug: same single show repeating
                last_name = all_shows[-1]["name"] if all_shows else ""
                if shows_on_page[0]["name"] == last_name:
                    stop_reason = "stale_entry_detected"
                    break

            all_shows.extend(shows_on_page)

            if page % 20 == 0:
                logger.info("BS: fetched %d pages, %d shows so far", page, len(all_shows))

            # Check for NEXT page link
            next_link = soup.find("a", string=re.compile(r"NEXT", re.IGNORECASE))
            if not next_link:
                stop_reason = "no_next_link"
                break
            page += 1

        logger.info("BS: pagination complete — %d pages, %d shows, stop_reason=%s",
                     page, len(all_shows), stop_reason)
        return all_shows

    def _parse_calendar_table(self, soup: BeautifulSoup, date_from: str) -> list[dict]:
        """Parse show rows from a calendar page. 4-column table: date|type|area|venue."""
        shows = []
        year = int(date_from.split("/")[2])

        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) != 4:
                continue

            detail_link = tds[3].find("a", href=re.compile(r"centre-detail\.cfm"))
            if not detail_link:
                continue

            date_text = tds[0].get_text(strip=True)
            show_type = tds[1].get_text(strip=True)
            area = tds[2].get_text(strip=True)
            show_name = detail_link.get_text(strip=True)
            detail_href = detail_link["href"]

            shid_match = re.search(r"shid=(\d+)", detail_href)
            show_id = shid_match.group(1) if shid_match else None

            parsed_date = self._parse_calendar_date(date_text, year)
            if not parsed_date:
                continue

            categories = self._extract_categories(show_type)
            has_pony = bool(categories & PONY_CATEGORIES)

            detail_url = detail_href if detail_href.startswith("http") else f"{BASE_URL}/{detail_href.lstrip('/')}"

            shows.append({
                "name": show_name,
                "date_text": parsed_date,
                "show_type": show_type,
                "area": area,
                "show_id": show_id,
                "detail_url": detail_url,
                "has_pony": has_pony,
                "categories": categories,
            })

        return shows

    def _deduplicate_multiday(self, shows: list[dict]) -> list[dict]:
        """Group multi-day shows by show_id, keep earliest date and latest date."""
        by_id: dict[str, dict] = {}
        for show in shows:
            sid = show.get("show_id")
            if not sid:
                by_id[f"_no_id_{id(show)}"] = show
                continue

            if sid in by_id:
                existing = by_id[sid]
                # Expand date range
                if show["date_text"] < existing["date_text"]:
                    existing["date_start_override"] = show["date_text"]
                if show["date_text"] > existing.get("date_end_override", existing["date_text"]):
                    existing["date_end_override"] = show["date_text"]
                # Merge categories
                existing["categories"] |= show["categories"]
                existing["has_pony"] = existing["has_pony"] or show["has_pony"]
            else:
                by_id[sid] = show.copy()

        return list(by_id.values())

    async def _enrich_from_detail(self, client: httpx.AsyncClient, show: dict) -> ExtractedCompetition:
        """Fetch detail page for postcode, lat/lng, date range, classes, fees, entry deadline."""
        resp = await client.get(show["detail_url"])
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        page_text = soup.get_text()

        # Extract postcode
        postcode = None
        postcode_match = POSTCODE_RE.search(page_text)
        if postcode_match:
            postcode = postcode_match.group(0).strip()

        # Extract lat/lng from Google Maps link
        maps_link = soup.find("a", href=re.compile(r"google\.com/maps"))
        latitude, longitude = None, None
        if maps_link:
            latlng_match = LATLNG_RE.search(maps_link["href"])
            if latlng_match:
                latitude = latlng_match.group(1)
                longitude = latlng_match.group(2)

        # Parse date range from h1: "VENUE - FRI 20 TO SUN 22 FEBRUARY 2026"
        date_start = show.get("date_start_override", show["date_text"])
        date_end = show.get("date_end_override")
        h1 = soup.find("h1")
        if h1:
            h1_text = h1.get_text(strip=True)
            date_range = self._parse_detail_date_range(h1_text)
            if date_range:
                date_start, date_end = date_range

        # Extract classes from schedule tables (9-column layout)
        classes = self._extract_classes(soup)

        # Check for pony classes in schedule
        has_pony = show["has_pony"]
        if not has_pony and classes:
            class_text = " ".join(classes).lower()
            if any(kw in class_text for kw in ["pony", "junior", "u18", "u16", "u14"]):
                has_pony = True

        name = self._build_event_name(show)

        return ExtractedCompetition(
            name=name,
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name=show["name"],
            venue_postcode=postcode,
            discipline="Show Jumping",
            has_pony_classes=has_pony,
            classes=classes,
            url=show["detail_url"],
        )

    def _build_basic_competition(self, show: dict) -> ExtractedCompetition | None:
        """Build a competition from calendar listing data only."""
        date_start = show.get("date_start_override", show.get("date_text"))
        if not date_start:
            return None

        name = self._build_event_name(show)

        return ExtractedCompetition(
            name=name,
            date_start=date_start,
            date_end=show.get("date_end_override"),
            venue_name=show["name"],
            venue_postcode=None,
            discipline="Show Jumping",
            has_pony_classes=show["has_pony"],
            classes=[],
            url=show["detail_url"],
        )

    def _build_event_name(self, show: dict) -> str:
        """Build a descriptive event name from show_type and venue.

        The BS calendar only provides venue name + show type (e.g. 'SENIOR (C2,CL,S)').
        We combine them into something like 'BS Show Jumping - Addington Equestrian Centre'.
        """
        venue = show["name"]
        show_type = show.get("show_type", "").strip()

        if show_type:
            # Extract the level (SENIOR, PONY, JUNIOR etc.) before the categories
            level = show_type.split("(")[0].strip()
            if level:
                return f"BS {level.title()} Show Jumping - {venue}"

        return f"BS Show Jumping - {venue}"

    def _parse_calendar_date(self, text: str, year: int) -> str | None:
        """Parse 'Fri 20th Feb' into YYYY-MM-DD."""
        cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text).strip()
        try:
            dt = datetime.strptime(f"{cleaned} {year}", "%a %d %b %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            match = re.search(r"(\d{1,2})\s+(\w+)", cleaned)
            if match:
                try:
                    dt = datetime.strptime(f"{match.group(1)} {match.group(2)} {year}", "%d %b %Y")
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass
        return None

    def _parse_detail_date_range(self, h1_text: str) -> tuple[str, str | None] | None:
        """Parse 'VENUE - FRI 20 TO SUN 22 FEBRUARY 2026' from the h1."""
        match = re.search(
            r"\w+\s+(\d{1,2})\s+TO\s+\w+\s+(\d{1,2})\s+(\w+)\s+(\d{4})",
            h1_text, re.IGNORECASE
        )
        if match:
            try:
                start = datetime.strptime(f"{match.group(1)} {match.group(3)} {match.group(4)}", "%d %B %Y")
                end = datetime.strptime(f"{match.group(2)} {match.group(3)} {match.group(4)}", "%d %B %Y")
                return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
            except ValueError:
                pass

        match = re.search(r"\w+\s+(\d{1,2})\s+(\w+)\s+(\d{4})", h1_text, re.IGNORECASE)
        if match:
            try:
                dt = datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %B %Y")
                return dt.strftime("%Y-%m-%d"), None
            except ValueError:
                pass

        return None

    def _extract_categories(self, show_type: str) -> set[str]:
        """Extract category codes from show type like 'SENIOR (C2,CL,S)'."""
        match = re.search(r"\(([^)]+)\)", show_type)
        if match:
            return {c.strip() for c in match.group(1).split(",")}
        return set()

    def _extract_classes(self, soup: BeautifulSoup) -> list[str]:
        """Extract class names from 9-column schedule tables."""
        classes = []
        for table in soup.find_all("table"):
            for tr in table.find_all("tr"):
                tds = tr.find_all("td")
                # Schedule table has 9 columns; class name is column 3 (index 2)
                if len(tds) >= 4:
                    class_text = tds[2].get_text(strip=True)
                    # Strip trailing 7-digit class ID
                    class_text = re.sub(r"\s+\d{7}$", "", class_text)
                    if class_text and len(class_text) > 5:
                        classes.append(class_text)
        return classes
