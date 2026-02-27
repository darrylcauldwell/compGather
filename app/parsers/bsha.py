from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from app.parsers.bases import TwoPhaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import extract_postcode
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

CALENDAR_URL = "https://bsha.online/index.php"

_DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)\s+(\w+)\s+(\d{4})", re.IGNORECASE,
)
_CONCURRENCY = 6


@register_parser("bsha")
class BSHAParser(TwoPhaseParser):
    """Parser for BSHA (British Show Horse Association) show calendar.

    Phase 1: Fetches 12 monthly calendar pages from bsha.online.
    Phase 2: Fetches entry/website links concurrently to enrich venue + postcode.
    """

    CONCURRENCY = _CONCURRENCY

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        today = date.today()
        stubs: list[dict] = []
        seen: set[str] = set()

        async with self._make_client() as client:
            for month in range(1, 13):
                try:
                    month_stubs = await self._scrape_month(client, month, today)
                    for stub in month_stubs:
                        key = f"{stub['name']}|{stub['date_start']}"
                        if key not in seen:
                            seen.add(key)
                            stubs.append(stub)
                except Exception as e:
                    logger.debug("BSHA: failed to scrape month %d: %s", month, e)

            logger.info("BSHA: %d shows from calendar, enriching venues...", len(stubs))
            competitions = await self._enrich_venues(client, stubs)

        self._log_result("BSHA", len(competitions))
        return competitions

    async def _scrape_month(self, client, month, today):
        soup = await self._fetch_html(client, CALENDAR_URL, params={"id": "74", "month": str(month)})
        stubs = []
        for card in soup.find_all("div", class_=re.compile(r"\bcard-4\b")):
            stub = self._parse_card(card, today)
            if stub:
                stubs.append(stub)
        return stubs

    def _parse_card(self, card, today):
        h4 = card.find("h4")
        if not h4:
            return None
        b = h4.find("b")
        name = (b.get_text(strip=True) if b else h4.get_text(strip=True))
        if not name:
            return None

        date_el = card.find("div", class_="smallfont")
        if not date_el:
            return None
        date_start, date_end = self._parse_date_text(date_el.get_text(strip=True))
        if not date_start:
            return None

        venue_name, venue_postcode = "TBC", None
        for attr_div in card.find_all("div", class_="showattr"):
            strong = attr_div.find("strong")
            if strong and "Venue" in strong.get_text():
                venue_text = re.sub(r"^Venue:\s*", "", attr_div.get_text(strip=True))
                if venue_text.strip():
                    venue_name = venue_text.strip()
                    venue_postcode = extract_postcode(venue_name)
                break

        links, event_url = [], None
        for a in card.find_all("a", class_="nodecor"):
            href = a.get("href", "")
            if not href or not href.startswith("http"):
                continue
            href = href.replace("\\", "/")
            link_text = a.get_text(strip=True)
            if "Entries" in link_text or "Website" in link_text:
                links.append(href)
                if not event_url:
                    event_url = href

        return {
            "name": name, "date_start": date_start,
            "date_end": date_end if date_end and date_end != date_start else None,
            "venue_name": venue_name, "venue_postcode": venue_postcode,
            "links": links, "event_url": event_url,
        }

    async def _enrich_venues(self, client, stubs):
        sem = asyncio.Semaphore(self.CONCURRENCY)

        async def enrich_one(stub):
            if stub["venue_name"] == "TBC" and stub["links"]:
                async with sem:
                    venue, postcode = await self._try_venue_from_links(client, stub["links"])
                    if venue:
                        stub["venue_name"] = venue
                    if postcode:
                        stub["venue_postcode"] = postcode
            return self._stub_to_comp(stub)

        return list(await asyncio.gather(*[enrich_one(s) for s in stubs]))

    async def _try_venue_from_links(self, client, links):
        for link in links:
            try:
                resp = await client.get(link, timeout=15.0)
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
                venue, postcode = self._extract_venue_from_page(soup, resp.text)
                if venue or postcode:
                    return venue, postcode
            except Exception as e:
                logger.debug("BSHA: venue fetch failed for %s: %s", link, e)
        return None, None

    def _extract_venue_from_page(self, soup, html):
        page_text = soup.get_text(" ", strip=True)
        _FIELD_BOUNDARY = (
            r"(?:\n|\r|Entry Fee|Entries Close|Entries Open|Contact:|Organis|Secretary|"
            r"Phone:|E-mail:|Email:|Judge|Class\b|Date:)"
        )

        for label in ["Venue:", "Location:", "Address:"]:
            pattern = label.replace(":", r":\s*") + r"(.+?)" + _FIELD_BOUNDARY
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                loc_text = match.group(1).strip().rstrip(".")
                postcode = extract_postcode(loc_text)
                if postcode:
                    idx = loc_text.upper().index(postcode.upper())
                    venue = loc_text[:idx].rstrip(" ,.-")
                else:
                    venue = loc_text
                if venue:
                    return venue, postcode

        postcode = extract_postcode(page_text)
        return None, postcode

    def _stub_to_comp(self, stub):
        return self._build_event(
            name=stub["name"], date_start=stub["date_start"], date_end=stub["date_end"],
            venue_name=stub["venue_name"], venue_postcode=stub["venue_postcode"],
            discipline="Showing",
            url=stub["event_url"] or CALENDAR_URL,
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
            return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %b %Y").strftime("%Y-%m-%d")
        except ValueError:
            return None
