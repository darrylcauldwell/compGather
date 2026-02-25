from __future__ import annotations

import logging
import re
from datetime import date, datetime

from app.parsers.bases import BROWSER_UA, HttpParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, extract_postcode, infer_discipline
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

CALENDAR_URL = "https://bsps.equine.events/index.php"

_DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)\s+(\w+)\s+(\d{4})",
    re.IGNORECASE,
)


@register_parser("bsps")
class BSPSParser(HttpParser):
    """Parser for BSPS (British Show Pony Society) show calendar.

    Fetches 12 monthly calendar pages from bsps.equine.events.
    """

    HEADERS = {"User-Agent": BROWSER_UA}

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        today = date.today()
        competitions: list[ExtractedEvent] = []
        seen: set[str] = set()

        async with self._make_client() as client:
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

        self._log_result("BSPS", len(competitions))
        return competitions

    async def _scrape_month(self, client, month, today):
        soup = await self._fetch_html(client, CALENDAR_URL, params={"id": "519", "month": str(month)})
        comps: list[ExtractedEvent] = []

        for card in soup.find_all("div", class_=re.compile(r"\bcard-4\b")):
            comp = self._parse_card(card, today)
            if comp:
                comps.append(comp)
        return comps

    def _parse_card(self, card, today):
        name_el = card.find("div", class_="regularfont")
        if not name_el:
            return None
        name = name_el.get_text(strip=True)
        if not name:
            return None

        date_el = card.find("div", class_="smallfont")
        if not date_el:
            return None
        date_text = date_el.get_text(strip=True)
        date_start, date_end = self._parse_date_text(date_text)
        if not date_start:
            return None

        venue_name = "TBC"
        venue_postcode = None
        for attr_div in card.find_all("div", class_="showattr"):
            strong = attr_div.find("strong")
            if strong and "Venue" in strong.get_text():
                venue_text = attr_div.get_text(strip=True)
                venue_text = re.sub(r"^Venue:\s*", "", venue_text)
                venue_name, venue_postcode = self._split_venue_postcode(venue_text)
                break

        event_url = None
        for a in card.find_all("a", class_="nodecor"):
            link_text = a.get_text(strip=True)
            if "Entries" in link_text or "Website" in link_text:
                href = a.get("href", "")
                if href and href.startswith("http"):
                    event_url = href.replace("\\", "/")
                    break

        has_pony = detect_pony_classes(name)
        discipline = infer_discipline(name) or "Showing"

        return self._build_event(
            name=name,
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name=venue_name,
            venue_postcode=venue_postcode,
            discipline=discipline,
            has_pony_classes=has_pony,
            url=event_url or CALENDAR_URL,
        )

    def _parse_date_text(self, text):
        matches = list(_DATE_RE.finditer(text))
        if not matches:
            return None, None
        date_start = self._match_to_iso(matches[0])
        date_end = self._match_to_iso(matches[-1]) if len(matches) > 1 else None
        return date_start, date_end

    def _match_to_iso(self, m):
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %b %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None

    def _split_venue_postcode(self, text):
        postcode = extract_postcode(text)
        if postcode:
            venue = text[:text.upper().index(postcode.upper())].rstrip(" -,")
            return venue.strip() or "TBC", postcode
        return text.strip() or "TBC", None
