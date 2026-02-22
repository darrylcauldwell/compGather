from __future__ import annotations

import logging
import re
from datetime import date, datetime

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import (
    detect_pony_classes,
    infer_discipline,
    is_competition_event,
    is_future_event,
)
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

BASE_URL = "https://www.arenauk.com"
CALENDAR_URL = f"{BASE_URL}/events/all-upcoming"
VENUE_NAME = "Arena Uk"
VENUE_POSTCODE = "NG32 2EF"

# How many months ahead to scan
MONTHS_AHEAD = 18

# Browser-like User-Agent required — WAF blocks bare requests
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

# Category slugs in URLs that indicate non-competition events
_SKIP_CATEGORIES = {"car-boot", "dog-agility", "training-clinics"}

# Map URL path segments to disciplines
_CATEGORY_DISCIPLINE = {
    "show-jumping": "Show Jumping",
    "dressage-events": "Dressage",
    "showing-events": "Showing",
    "mounted-games": "Gymkhana",
    "indoor-carriage-driving": "Driving",
    "pony-club": "Pony Club",
}


@register_parser("arena_uk")
class ArenaUKParser(BaseParser):
    """Parser for arenauk.com — Joomla with Events Booking Pro.

    Scrapes the monthly calendar view. Each month is a separate page
    at /events/all-upcoming?month=M&year=YYYY. Multi-day events appear
    in multiple day cells — first/last appearance gives start/end dates.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=30.0, headers=HEADERS
        ) as client:
            today = date.today()
            # Track events by URL: {url: {name, dates[], category}}
            event_map: dict[str, dict] = {}

            year, month = today.year, today.month
            for i in range(MONTHS_AHEAD):
                try:
                    events = await self._fetch_calendar_month(client, year, month)
                    for href, name, event_date, category in events:
                        if href not in event_map:
                            event_map[href] = {
                                "name": name,
                                "dates": [],
                                "category": category,
                            }
                        event_map[href]["dates"].append(event_date)
                except Exception as e:
                    logger.warning("Arena UK: failed to fetch %d-%02d: %s", year, month, e)

                month += 1
                if month > 12:
                    month = 1
                    year += 1

            logger.info("Arena UK: %d unique events from %d months", len(event_map), MONTHS_AHEAD)

            # Convert to competitions
            competitions: list[ExtractedCompetition] = []
            for href, info in event_map.items():
                comp = self._build_competition(href, info)
                if comp:
                    competitions.append(comp)

        logger.info("Arena UK: extracted %d competitions", len(competitions))
        return competitions

    async def _fetch_calendar_month(
        self, client: httpx.AsyncClient, year: int, month: int
    ) -> list[tuple[str, str, str, str]]:
        """Fetch a calendar month and extract (href, name, date, category) tuples."""
        resp = await client.get(CALENDAR_URL, params={"month": month, "year": year})
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[tuple[str, str, str, str]] = []

        for li in soup.select("li.eb-calendarDay"):
            # Extract the date from the day cell
            event_date = self._parse_day_cell_date(li, year, month)
            if not event_date:
                continue

            # Extract event links within this day
            for link in li.select("a.eb_event_link"):
                href = link.get("href", "")
                name = (link.get("title") or link.get_text(strip=True) or "").strip()
                if not href or not name:
                    continue

                # Normalise to relative path
                if href.startswith(BASE_URL):
                    href = href[len(BASE_URL):]

                # Extract category from URL path
                category = self._extract_category(href)

                results.append((href, name, event_date, category))

        return results

    def _parse_day_cell_date(self, li_tag, year: int, month: int) -> str | None:
        """Extract YYYY-MM-DD from a calendar day cell.

        The cell contains: <span class="day">Friday,</span> <span class="month">February</span> 21
        """
        date_div = li_tag.select_one("div.date.day_cell")
        if not date_div:
            return None

        month_span = date_div.select_one("span.month")
        if not month_span:
            return None

        month_name = month_span.get_text(strip=True)
        # The day number is a text node after the month span
        text = date_div.get_text(separator=" ", strip=True)
        day_match = re.search(r"(\d{1,2})\s*$", text)
        if not day_match:
            return None

        day = int(day_match.group(1))

        try:
            month_num = datetime.strptime(month_name, "%B").month
            return date(year, month_num, day).isoformat()
        except (ValueError, TypeError):
            return None

    def _extract_category(self, href: str) -> str:
        """Extract category slug from event URL path."""
        # URLs like /events/by-discipline/show-jumping/event-slug
        # or /events/all-upcoming/car-boot/event-slug
        parts = [p for p in href.split("/") if p]
        for part in parts:
            if part in _CATEGORY_DISCIPLINE or part in _SKIP_CATEGORIES:
                return part
        # Check broader patterns
        for part in parts:
            if part in (
                "show-jumping", "dressage-events", "showing-events",
                "mounted-games", "indoor-carriage-driving", "pony-club",
                "british-riding-clubs", "other-events",
                "car-boot", "dog-agility", "training-clinics",
            ):
                return part
        return ""

    def _build_competition(self, href: str, info: dict) -> ExtractedCompetition | None:
        """Convert collected event data into an ExtractedCompetition."""
        name = info["name"]
        category = info["category"]
        dates = sorted(info["dates"])

        if not dates:
            return None

        date_start = dates[0]
        date_end = dates[-1] if len(dates) > 1 and dates[-1] != dates[0] else None

        # Filter past events
        if not is_future_event(date_start, date_end):
            return None

        # Filter non-competition categories
        if category in _SKIP_CATEGORIES:
            return None

        # Filter non-competition event names
        if not is_competition_event(name):
            return None

        # Determine discipline
        discipline = _CATEGORY_DISCIPLINE.get(category) or infer_discipline(name)
        has_pony = detect_pony_classes(name) or category == "pony-club"

        event_url = f"{BASE_URL}{href}" if href.startswith("/") else href

        return ExtractedCompetition(
            name=name,
            date_start=date_start,
            date_end=date_end,
            venue_name=VENUE_NAME,
            venue_postcode=VENUE_POSTCODE,
            discipline=discipline,
            has_pony_classes=has_pony,
            classes=[],
            url=event_url,
        )
