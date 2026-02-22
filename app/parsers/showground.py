from __future__ import annotations

import html
import logging
import re
from datetime import date, datetime

import httpx

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

BASE_URL = "https://www.theshowground.com"
VENUE_NAME = "The Showground"
VENUE_POSTCODE = "NP26 5XP"
VENUE_LAT = 51.5991
VENUE_LNG = -2.735797

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# Pages to scrape — Wales & West shows + Cricklands shows
SHOW_PAGES = [
    "/walesandwestshows",
    "/cricklands",
]

# Date range: "3rd - 5th April", "22nd - 25th May"
_DATE_RANGE_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s*-\s*(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)",
    re.IGNORECASE,
)


@register_parser("showground")
class ShowgroundParser(BaseParser):
    """Parser for theshowground.com — Wix site, HTML scraping.

    Single venue: Mount Ballan Manor, Crick, Nr Chepstow (NP26 5XP).
    Shows are listed on two pages: Wales & West and Cricklands.
    Wix renders show data in rich-text components within a repeater.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=30.0, headers=HEADERS
        ) as client:
            competitions: list[ExtractedCompetition] = []

            for page_path in SHOW_PAGES:
                page_url = f"{BASE_URL}{page_path}"
                try:
                    resp = await client.get(page_url)
                    resp.raise_for_status()
                    shows = self._extract_shows(resp.text, page_path)
                    competitions.extend(shows)
                except Exception as e:
                    logger.warning("Showground: failed to fetch %s: %s", page_url, e)

        logger.info("Showground: extracted %d competitions", len(competitions))
        return competitions

    def _extract_shows(self, page_html: str, page_path: str) -> list[ExtractedCompetition]:
        """Extract shows from a Wix page by finding date patterns and nearby titles."""
        competitions: list[ExtractedCompetition] = []
        seen: set[str] = set()

        # Find all date ranges in the HTML
        for date_match in _DATE_RANGE_RE.finditer(page_html):
            start_day = int(date_match.group(1))
            end_day = int(date_match.group(2))
            month_name = date_match.group(3)

            # Look backwards for the title (nearest rich-text content before this date)
            search_start = max(0, date_match.start() - 500)
            before = page_html[search_start:date_match.start()]
            titles = re.findall(
                r'class="wixui-rich-text__text">([^<]{3,})<', before
            )
            if not titles:
                continue
            title = html.unescape(titles[-1].strip())

            # Look forwards for the description
            after = page_html[date_match.end():date_match.end() + 500]
            descs = re.findall(
                r'class="wixui-rich-text__text">([^<]{10,})<', after
            )
            description = html.unescape(descs[0].strip()) if descs else ""

            # Infer year — assume current year if month is ahead, next year otherwise
            year = self._infer_year(month_name)

            # Parse dates
            try:
                date_start = datetime.strptime(
                    f"{start_day} {month_name} {year}", "%d %B %Y"
                ).date()
                date_end = datetime.strptime(
                    f"{end_day} {month_name} {year}", "%d %B %Y"
                ).date()
            except ValueError:
                continue

            date_start_str = date_start.isoformat()
            date_end_str = date_end.isoformat()

            if not is_future_event(date_start_str, date_end_str):
                continue

            # Deduplicate by title + date
            key = f"{title}|{date_start_str}"
            if key in seen:
                continue
            seen.add(key)

            if not is_competition_event(title):
                continue

            text = f"{title} {description}"
            discipline = infer_discipline(text)
            has_pony = detect_pony_classes(text)

            # This venue is primarily show jumping — default if not otherwise detected
            if not discipline:
                discipline = "Show Jumping"

            # Build detail page URL from known page slugs
            detail_url = self._build_detail_url(title, page_path)

            competitions.append(ExtractedCompetition(
                name=title,
                date_start=date_start_str,
                date_end=date_end_str if date_end_str != date_start_str else None,
                venue_name=VENUE_NAME,
                venue_postcode=VENUE_POSTCODE,
                latitude=VENUE_LAT,
                longitude=VENUE_LNG,
                discipline=discipline,
                has_pony_classes=has_pony,
                classes=[],
                url=detail_url,
            ))

        return competitions

    def _infer_year(self, month_name: str) -> int:
        """Infer the year for a show based on the month.

        If the month is in the past, assume next year.
        """
        today = date.today()
        month_num = datetime.strptime(month_name, "%B").month
        if month_num < today.month:
            return today.year + 1
        if month_num == today.month:
            # Could be this year or next — assume this year
            return today.year
        return today.year

    def _build_detail_url(self, title: str, page_path: str) -> str:
        """Build a detail page URL from the show title."""
        # Known mappings from investigation
        slug_map = {
            "the welsh masters": "/welshmasters",
            "chepstow spring international": "/chepstowspringinternational",
            "chepstow summer international": "/chepstowsummerinternational",
            "second rounds show": "/secondrounds",
            "midsummer festival": "/midsummerfestival",
            "welsh home pony": "/welshhomepony",
            "june mixed show": "/junemixedshow",
            "april mixed show": "/aprilmixedshow",
            "may summer show": "/maysummershow",
            "july summer show": "/july-summer-show",
            "cricklands derby show": "/cricklands-derby-show",
            "halloween show": "/halloween-show",
            "end of season derby show": "/endofseasonderbyshow",
        }
        slug = slug_map.get(title.lower())
        if slug:
            return f"{BASE_URL}{slug}"
        return f"{BASE_URL}{page_path}"
