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
    extract_postcode,
    infer_discipline,
    is_future_event,
)
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

CALENDAR_URL = "https://bsps.equine.events/index.php"

# Ordinal date regex: "Sunday 1st Mar 2026"
_DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)\s+(\w+)\s+(\d{4})",
    re.IGNORECASE,
)

# Category CSS classes on card divs
_CATEGORY_MAP = {
    "Winter": "Showing",
    "Summer": "Showing",
    "RIHS": "Showing",
    "Liv-Semi": "Showing",
    "Liv-Final": "Showing",
}


@register_parser("bsps")
class BSPSParser(BaseParser):
    """Parser for BSPS (British Show Pony Society) show calendar.

    Fetches 12 monthly calendar pages from bsps.equine.events.
    Each page has server-rendered show cards with venue + postcode.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        today = date.today()
        competitions: list[ExtractedCompetition] = []
        seen: set[str] = set()  # dedup key: name + date_start

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": "EquiCalendar/1.0"},
        ) as client:
            for month in range(1, 13):
                try:
                    comps = await self._scrape_month(client, month, today)
                    for c in comps:
                        key = f"{c.name}|{c.date_start}"
                        if key not in seen:
                            seen.add(key)
                            competitions.append(c)
                except Exception as e:
                    logger.debug("BSPS: failed to scrape month %d: %s", month, e)

        logger.info("BSPS: %d competitions extracted", len(competitions))
        return competitions

    async def _scrape_month(
        self, client: httpx.AsyncClient, month: int, today: date
    ) -> list[ExtractedCompetition]:
        """Scrape a single month's calendar page."""
        resp = await client.get(CALENDAR_URL, params={"id": "519", "month": str(month)})
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        comps: list[ExtractedCompetition] = []

        for card in soup.find_all("div", class_=re.compile(r"\bcard-4\b")):
            comp = self._parse_card(card, today)
            if comp:
                comps.append(comp)

        return comps

    def _parse_card(self, card, today: date) -> ExtractedCompetition | None:
        """Parse a single BSPS show card."""
        # Show name from div.regularfont
        name_el = card.find("div", class_="regularfont")
        if not name_el:
            return None
        name = name_el.get_text(strip=True)
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

        # Venue + postcode from showattr div containing "Venue:"
        venue_name = "TBC"
        venue_postcode = None
        for attr_div in card.find_all("div", class_="showattr"):
            strong = attr_div.find("strong")
            if strong and "Venue" in strong.get_text():
                venue_text = attr_div.get_text(strip=True)
                # Strip "Venue:" prefix
                venue_text = re.sub(r"^Venue:\s*", "", venue_text)
                venue_name, venue_postcode = self._split_venue_postcode(venue_text)
                break

        # Website URL from entry/website link
        event_url = None
        for a in card.find_all("a", class_="nodecor"):
            link_text = a.get_text(strip=True)
            if "Entries" in link_text or "Website" in link_text:
                href = a.get("href", "")
                if href and href.startswith("http"):
                    event_url = href.replace("\\", "/")
                    break

        # Pony detection
        has_pony = detect_pony_classes(name)

        # Discipline: BSPS is primarily Showing
        discipline = infer_discipline(name) or "Showing"

        return ExtractedCompetition(
            name=name,
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name=venue_name,
            venue_postcode=venue_postcode,
            discipline=discipline,
            has_pony_classes=has_pony,
            url=event_url or CALENDAR_URL,
        )

    def _parse_date_text(self, text: str) -> tuple[str | None, str | None]:
        """Parse date text like 'Sunday 1st Mar 2026' or range with ' - ' separator."""
        matches = list(_DATE_RE.finditer(text))
        if not matches:
            return None, None

        date_start = self._match_to_iso(matches[0])
        date_end = self._match_to_iso(matches[-1]) if len(matches) > 1 else None

        return date_start, date_end

    def _match_to_iso(self, m: re.Match) -> str | None:
        """Convert a regex match (day, month_abbrev, year) to ISO date string."""
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %b %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None

    def _split_venue_postcode(self, text: str) -> tuple[str, str | None]:
        """Split 'Venue Name - POSTCODE' into (name, postcode).

        Handles formats like:
        - "Moorhouse Equestrian Centre - DN6 7HA"
        - "Pencoed Agricultural College, Pencoed Campus, Pencoed CF35 5LG"
        - "West Wilts Ec - Ba14 6Qt"
        """
        postcode = extract_postcode(text)
        if postcode:
            # Remove postcode and trailing separator from venue name
            venue = text[: text.upper().index(postcode.upper())].rstrip(" -,")
            return venue.strip() or "TBC", postcode
        return text.strip() or "TBC", None
