from __future__ import annotations

import logging
import re
from datetime import datetime

from app.parsers.bases import TwoPhaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import extract_postcode, normalise_venue_name
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

COMPETITIONS_URL = "https://www.nsea.org.uk/competitions/"

_AT_VENUE_RE = re.compile(
    r"@\s+(.+?)"
    r"(?:\s+\d{1,2}(?:st|nd|rd|th)?(?:[/\s]\d{1,2})?(?:\s+\w+)?(?:\s+\d{4})?)?$"
)


@register_parser("nsea")
class NSEAParser(TwoPhaseParser):
    """Parser for nsea.org.uk — National Schools Equestrian Association."""

    CONCURRENCY = 6

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        async with self._make_client() as client:
            stubs = await self._parse_listings(client, url)
            logger.info("NSEA: %d events from listing table", len(stubs))

            with_detail = [s for s in stubs if s.get("detail_url")]
            without_detail = [s for s in stubs if not s.get("detail_url")]

            competitions = await self._concurrent_fetch(
                with_detail,
                lambda stub: self._enrich_from_detail(client, stub),
                fallback_fn=self._build_from_stub,
            )
            for s in without_detail:
                comp = self._build_from_stub(s)
                if comp:
                    competitions.append(comp)

        self._log_result("NSEA", len(competitions))
        return competitions

    async def _parse_listings(self, client, url):
        soup = await self._fetch_html(client, url)
        stubs = []

        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue

            if len(tds) >= 5:
                date_text = tds[0].get_text(strip=True)
                name_tag = tds[1].find("a")
                name = name_tag.get_text(strip=True) if name_tag else tds[1].get_text(strip=True)
                detail_url = self._resolve_url(name_tag["href"]) if name_tag and name_tag.get("href") else None
                location = tds[2].get_text(strip=True)
            else:
                date_text = tds[0].get_text(strip=True)
                name_tag = tds[1].find("a")
                name = name_tag.get_text(strip=True) if name_tag else tds[1].get_text(strip=True)
                detail_url = self._resolve_url(name_tag["href"]) if name_tag and name_tag.get("href") else None
                location = tds[2].get_text(strip=True) if len(tds) > 2 else ""

            if not name or not date_text:
                continue

            date_start, date_end = self._parse_date_cell(date_text)
            if not date_start:
                continue

            name_lower = name.lower()
            if any(kw in name_lower for kw in ("pop up dressage", "nsea numbers", "virtual")):
                venue = "Online"
            else:
                venue = location if location else "TBC"
                at_match = _AT_VENUE_RE.search(name)
                if at_match:
                    venue = normalise_venue_name(at_match.group(1).strip())

            stubs.append({
                "name": name, "date_start": date_start, "date_end": date_end,
                "venue_name": venue, "detail_url": detail_url,
                "discipline": None,
            })

        return stubs

    async def _enrich_from_detail(self, client, stub):
        url = stub["detail_url"]
        soup = await self._fetch_html(client, url)
        page_text = soup.get_text()

        venue_name = stub["venue_name"]
        venue_postcode = None

        if venue_name.lower() != "online":
            venue_heading = soup.find("h3", string=re.compile(r"The Venue", re.IGNORECASE))
            if venue_heading:
                next_p = venue_heading.find_next_sibling("p")
                if next_p:
                    venue_text = next_p.get_text(separator=", ", strip=True)
                    venue_parts = [p.strip() for p in venue_text.split(",") if p.strip()]
                    if venue_parts:
                        venue_name = venue_parts[0]
                    venue_postcode = extract_postcode(venue_text)

        if not venue_postcode and venue_name.lower() != "online":
            venue_postcode = extract_postcode(page_text)

        classes = self._extract_classes(soup)

        return self._build_event(
            name=stub["name"], date_start=stub["date_start"], date_end=stub["date_end"],
            venue_name=venue_name, venue_postcode=venue_postcode,
            discipline=stub["discipline"],
            classes=classes,
            url=url,
        )

    def _build_from_stub(self, stub):
        if not stub.get("date_start") or not stub.get("name"):
            return None
        return self._build_event(
            name=stub["name"], date_start=stub["date_start"], date_end=stub.get("date_end"),
            venue_name=stub.get("venue_name", "TBC"),
            discipline=stub.get("discipline"),
            url=stub.get("detail_url") or COMPETITIONS_URL,
        )

    def _parse_date_cell(self, text):
        text = text.strip()
        range_match = re.match(
            r"(\d{1,2}\s+\w+\s+\d{4})\s*[-–]\s*(\d{1,2}\s+\w+\s+\d{4})", text
        )
        if range_match:
            start = self._parse_single_date(range_match.group(1))
            end = self._parse_single_date(range_match.group(2))
            return start, end
        return self._parse_single_date(text), None

    def _parse_single_date(self, text):
        text = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text.strip())
        for fmt in ["%d %b %Y", "%d %B %Y"]:
            try:
                return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def _extract_classes(self, soup):
        classes = []
        for heading in soup.find_all(["h2", "h3", "h4", "h5"]):
            text = heading.get_text(strip=True)
            if re.match(r"Class\s+\d", text, re.IGNORECASE):
                classes.append(text)
        if not classes:
            for table in soup.find_all("table"):
                for tr in table.find_all("tr"):
                    for td in tr.find_all("td"):
                        text = td.get_text(strip=True)
                        if re.match(r"Class\s+\d", text, re.IGNORECASE) and len(text) > 5:
                            classes.append(text)
        if not classes:
            for li in soup.find_all("li"):
                text = li.get_text(strip=True)
                if re.match(r"Class\s+\d", text, re.IGNORECASE):
                    classes.append(text)
        return classes

    def _resolve_url(self, href):
        if href.startswith("http"):
            return href
        return f"https://www.nsea.org.uk{href}" if href.startswith("/") else f"https://www.nsea.org.uk/{href}"
