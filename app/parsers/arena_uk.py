from __future__ import annotations

import logging
import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from app.parsers.bases import BROWSER_UA, SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

CALENDAR_PATH = "/events/all-upcoming"
MONTHS_AHEAD = 18

_SKIP_CATEGORIES = {"car-boot", "dog-agility"}

_CATEGORY_DISCIPLINE = {
    "show-jumping": "Show Jumping",
    "dressage-events": "Dressage",
    "showing-events": "Showing",
    "mounted-games": "Gymkhana",
    "indoor-carriage-driving": "Driving",
    "pony-club": "Pony Club",
}


@register_parser("arena_uk")
class ArenaUKParser(SingleVenueParser):
    """Parser for arenauk.com — Joomla with Events Booking Pro.

    Scrapes the monthly calendar view. Multi-day events appear in
    multiple day cells — first/last appearance gives start/end dates.
    """

    VENUE_NAME = "Arena Uk"
    VENUE_POSTCODE = "NG32 2EF"
    BASE_URL = "https://www.arenauk.com"
    HEADERS = {
        "User-Agent": BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml",
    }

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        async with self._make_client() as client:
            today = date.today()
            event_map: dict[str, dict] = {}

            year, month = today.year, today.month
            for _i in range(MONTHS_AHEAD):
                try:
                    soup = await self._fetch_html(
                        client,
                        f"{self.BASE_URL}{CALENDAR_PATH}",
                        params={"month": month, "year": year},
                    )
                    for href, name, event_date, category in self._parse_month(soup, year, month):
                        if href not in event_map:
                            event_map[href] = {"name": name, "dates": [], "category": category}
                        event_map[href]["dates"].append(event_date)
                except Exception as e:
                    logger.warning("Arena UK: failed to fetch %d-%02d: %s", year, month, e)

                month += 1
                if month > 12:
                    month = 1
                    year += 1

            logger.info("Arena UK: %d unique events from %d months", len(event_map), MONTHS_AHEAD)

            competitions = []
            for href, info in event_map.items():
                comp = self._build_competition(href, info)
                if comp:
                    competitions.append(comp)

        self._log_result("Arena UK", len(competitions))
        return competitions

    def _parse_month(self, soup: BeautifulSoup, year: int, month: int):
        results = []
        for li in soup.select("li.eb-calendarDay"):
            event_date = self._parse_day_cell_date(li, year, month)
            if not event_date:
                continue

            for link in li.select("a.eb_event_link"):
                href = link.get("href", "")
                name = (link.get("title") or link.get_text(strip=True) or "").strip()
                if not href or not name:
                    continue

                if href.startswith(self.BASE_URL):
                    href = href[len(self.BASE_URL):]

                category = self._extract_category(href)
                results.append((href, name, event_date, category))

        return results

    def _parse_day_cell_date(self, li_tag, year, month):
        date_div = li_tag.select_one("div.date.day_cell")
        if not date_div:
            return None

        month_span = date_div.select_one("span.month")
        if not month_span:
            return None

        month_name = month_span.get_text(strip=True)
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

    def _extract_category(self, href):
        parts = [p for p in href.split("/") if p]
        for part in parts:
            if part in _CATEGORY_DISCIPLINE or part in _SKIP_CATEGORIES:
                return part
        for part in parts:
            if part in (
                "show-jumping", "dressage-events", "showing-events",
                "mounted-games", "indoor-carriage-driving", "pony-club",
                "british-riding-clubs", "other-events",
                "car-boot", "dog-agility", "training-clinics",
            ):
                return part
        return ""

    def _build_competition(self, href, info):
        name = info["name"]
        category = info["category"]
        dates = sorted(info["dates"])

        if not dates or category in _SKIP_CATEGORIES:
            return None

        date_start = dates[0]
        date_end = dates[-1] if len(dates) > 1 and dates[-1] != dates[0] else None

        discipline = _CATEGORY_DISCIPLINE.get(category)
        event_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href

        return self._build_event(
            name=name,
            date_start=date_start,
            date_end=date_end,
            discipline=discipline,
            url=event_url,
        )
