"""Parser for Endurance GB events calendar.

Uses Playwright to load the Knockout.js-based events page and wait for
dynamic event content to render.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.parsers.bases import PlaywrightParser
from app.parsers.registry import register_parser
from app.parsers.utils import extract_postcode, normalise_postcode
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

ENDURANCE_GB_URL = "https://www.endurancegb.co.uk/Events/Calendar"


@register_parser("endurance_gb")
class EnduranceGBParser(PlaywrightParser):
    """Parser for Endurance GB events calendar.

    Uses Playwright to load the Knockout.js-based page and wait for
    event data to be dynamically rendered.
    """

    WAIT_STRATEGY = "domcontentloaded"
    EXTRA_WAIT_MS = 3000
    TIMEOUT_MS = 60000

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        event_html = await self._render_page(ENDURANCE_GB_URL)
        if not event_html:
            logger.warning("Endurance GB: no content received")
            return []

        competitions = self._parse_event_html(event_html)
        self._log_result("Endurance GB", len(competitions))
        return competitions

    def _parse_event_html(self, html: str) -> list[ExtractedEvent]:
        soup = BeautifulSoup(html, "html.parser")
        competitions: list[ExtractedEvent] = []
        seen: set[tuple[str, str]] = set()

        event_elements = soup.find_all(["div", "article", "li"], class_=re.compile(r"event|item|card", re.I))
        logger.info("Endurance GB: found %d potential event elements", len(event_elements))

        for element in event_elements:
            competition = self._parse_event_element(element)
            if competition:
                key = (competition.name, competition.date_start)
                if key not in seen:
                    seen.add(key)
                    competitions.append(competition)

        return competitions

    def _parse_event_element(self, element) -> ExtractedEvent | None:
        try:
            text = element.get_text(separator=" ", strip=True)
            if not text or len(text) < 10:
                return None

            date_match = re.search(
                r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{4})",
                text, re.IGNORECASE,
            )
            if not date_match:
                date_match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
            if not date_match:
                return None

            date_str = self._parse_date_match(date_match)
            if not date_str:
                return None

            name_elem = element.find(["strong", "b", "h3", "h4", "h5"])
            name = name_elem.get_text(strip=True) if name_elem else text[:50].split("\n")[0]
            if not name or len(name) < 3:
                return None

            venue_postcode = extract_postcode(text)
            venue_postcode = normalise_postcode(venue_postcode)

            return self._build_event(
                name=name[:100],
                date_start=date_str,
                venue_name="Endurance GB",
                venue_postcode=venue_postcode,
                discipline="Endurance",
                url=ENDURANCE_GB_URL,
            )
        except (AttributeError, TypeError, ValueError):
            return None

    def _parse_date_match(self, match):
        try:
            day = match.group(1)
            month_or_num = match.group(2)
            year = match.group(3)

            if month_or_num.isdigit():
                try:
                    dt = datetime.strptime(f"{day}/{month_or_num}/{year}", "%d/%m/%Y")
                except ValueError:
                    return None
            else:
                try:
                    dt = datetime.strptime(f"{day} {month_or_num[:3]} {year}", "%d %b %Y")
                except ValueError:
                    return None

            return dt.strftime("%Y-%m-%d")
        except (ValueError, IndexError, AttributeError):
            return None
