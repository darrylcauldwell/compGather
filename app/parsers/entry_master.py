"""Parser for entrymaster.online Pony Club competitions.

Scrapes Pony Club area competitions and nationals from entrymaster.online.
Each subdomain hosts a list of events as div.event blocks with dates, venues,
and booking links.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

from app.parsers.bases import HttpParser
from app.parsers.registry import register_parser
from app.parsers.utils import extract_postcode
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

ENTRYMASTER_AREAS = [
    ("pc.entrymaster.online", "National", None),
    ("pcarea1.entrymaster.online", "Area 1", "1"),
    ("pcarea2.entrymaster.online", "Area 2", "2"),
    ("pcarea3.entrymaster.online", "Area 3", "3"),
    ("pcarea4.entrymaster.online", "Area 4", "4"),
    ("pcarea5.entrymaster.online", "Area 5", "5"),
    ("pcarea6.entrymaster.online", "Area 6", "6"),
    ("pcarea7.entrymaster.online", "Area 7", "7"),
    ("pcarea8.entrymaster.online", "Area 8", "8"),
    ("pcarea9.entrymaster.online", "Area 9", "9"),
    ("pcarea9raceday.entrymaster.online", "Area 9 Raceday", "9R"),
    ("pcarea10.entrymaster.online", "Area 10", "10"),
    ("pcarea11.entrymaster.online", "Area 11", "11"),
    ("pcarea12.entrymaster.online", "Area 12", "12"),
    ("pcarea13.entrymaster.online", "Area 13", "13"),
    ("pcarea14.entrymaster.online", "Area 14", "14"),
    ("pcarea15.entrymaster.online", "Area 15", "15"),
    ("pcarea16.entrymaster.online", "Area 16", "16"),
    ("pctetrathlon.entrymaster.online", "National Tetrathlon", "Tetra"),
    ("area5tetrathlon.entrymaster.online", "Area 5 Tetrathlon", "5T"),
    ("cravenpc.entrymaster.online", "Craven PC", "Craven"),
]

# Date patterns: "Saturday 20th June 2026", "Monday 10th November 2025 - Thursday 31st December 2026"
_DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})",
    re.IGNORECASE,
)


@register_parser("entry_master")
class EntryMasterParser(HttpParser):
    """Parser for entrymaster.online Pony Club competitions.

    Each area subdomain has a page with div.event blocks containing
    event title, dates, venue, and booking links.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        seen: set[tuple[str, str, str]] = set()
        competitions: list[ExtractedEvent] = []

        async with self._make_client() as client:
            for subdomain, area_name, area_code in ENTRYMASTER_AREAS:
                try:
                    area_events = await self._scrape_area(client, subdomain, area_name)
                    for comp in area_events:
                        key = (comp.name, comp.date_start, comp.venue_name)
                        if key not in seen:
                            seen.add(key)
                            competitions.append(comp)
                    logger.info("EntryMaster: %d events from %s (%s)", len(area_events), area_name, subdomain)
                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.debug("EntryMaster: failed to scrape %s: %s", area_name, e)

        self._log_result("EntryMaster", len(competitions))
        return competitions

    async def _scrape_area(self, client, subdomain, area_name):
        """Fetch and parse events from a single EntryMaster subdomain."""
        base_url = f"https://{subdomain}/index.php"

        try:
            soup = await self._fetch_html(client, base_url)
        except Exception:
            return []

        competitions: list[ExtractedEvent] = []

        # Events are in <div class="event type_XX"> blocks
        for event_div in soup.find_all("div", class_=re.compile(r"^event\s+type_")):
            comp = self._parse_event_block(event_div, subdomain, area_name)
            if comp:
                competitions.append(comp)

        return competitions

    def _parse_event_block(self, event_div, subdomain, area_name):
        """Parse a single event block from the EntryMaster page.

        Structure:
          <div class="event type_XX">
            <div id="eventNNN" class="w3-cell-row">
              <div class="w3-cell">
                <div class="...bigfont">EVENT TITLE</div>
              </div>
              <div>
                <a class="nodecor" href="index.php?id=85&event=NNN">Enter Online</a>
              </div>
            </div>
            <div class="w3-padding-small w3-white...">
              <div class="w3-padding w3-text-em-red regularfont"><b>DATE TEXT</b></div>
              <div>Venue: <b>VENUE NAME, POSTCODE</b></div>
            </div>
          </div>
        """
        # Extract title from the bigfont div
        title_div = event_div.find("div", class_=re.compile(r"bigfont"))
        if not title_div:
            return None
        name = title_div.get_text(strip=True)
        if not name or len(name) < 3:
            return None

        # Extract date from the red date div
        date_div = event_div.find("div", class_=re.compile(r"w3-text-em-red.*regularfont|regularfont.*w3-text-em-red"))
        if not date_div:
            return None
        date_text = date_div.get_text(strip=True)
        date_start, date_end = self._parse_em_date_range(date_text)
        if not date_start:
            return None

        # Extract venue from "Venue: <b>...</b>" text
        venue_name = "TBC"
        venue_postcode = None
        for div in event_div.find_all("div", recursive=True):
            # Find the specific div that contains "Venue:" as direct text
            if div.find("div"):
                # Skip container divs — only match leaf divs
                continue
            text = div.get_text(strip=True)
            if text.startswith("Venue:"):
                # Extract value from <b> tag if present
                b_tag = div.find("b")
                venue_text = b_tag.get_text(" ", strip=True) if b_tag else text[6:].strip()
                venue_text = re.sub(r"\s+", " ", venue_text)  # collapse whitespace
                venue_postcode = extract_postcode(venue_text)
                if venue_postcode:
                    idx = venue_text.upper().index(venue_postcode.upper())
                    venue_name = venue_text[:idx].rstrip(" ,")
                else:
                    venue_name = venue_text
                venue_name = venue_name.strip() or "TBC"
                break

        # Extract booking URL
        booking_url = f"https://{subdomain}/index.php"
        link = event_div.find("a", class_="nodecor", href=re.compile(r"event="))
        if link:
            href = link.get("href", "")
            if href and not href.startswith("http"):
                booking_url = f"https://{subdomain}/{href}"
            elif href:
                booking_url = href

        final_name = f"{name} ({area_name})" if area_name != "National" else name

        return self._build_event(
            name=final_name,
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name=venue_name,
            venue_postcode=venue_postcode,
            has_pony_classes=True,
            url=booking_url,
        )

    def _parse_em_date_range(self, text):
        """Parse EntryMaster date text like 'Saturday 20th June 2026' or date ranges."""
        matches = list(_DATE_RE.finditer(text))
        if not matches:
            return None, None

        date_start = self._match_to_iso(matches[0])
        date_end = self._match_to_iso(matches[-1]) if len(matches) > 1 else None
        return date_start, date_end

    def _match_to_iso(self, m):
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None
