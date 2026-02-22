from __future__ import annotations

import asyncio
import logging
import re
from datetime import date

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import extract_postcode, is_future_event
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://outdoorshows.co.uk/page-sitemap.xml"
BASE_URL = "https://outdoorshows.co.uk"

# Slugs to skip (non-event pages)
_SKIP_SLUGS = {
    "/", "/gdpr/", "/covid19/", "/coming-2019/", "/holding-page/",
    "/sliddeshow/", "/abbey-farm-popup-campsite/",
}

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

_MONTH_NAMES = "|".join(_MONTH_MAP.keys())

# Single month dates: "5th & 6th September", "29th 30th & 31st August", "14th June"
_DATES_SINGLE_MONTH_RE = re.compile(
    r"((?:\d{1,2}(?:st|nd|rd|th)[\s,&]*)+)\s+"
    rf"({_MONTH_NAMES})",
    re.IGNORECASE,
)

# Cross-month: "31st July 1st & 2nd August"
_DATES_CROSS_MONTH_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)\s+"
    rf"({_MONTH_NAMES})\s+"
    r"((?:\d{1,2}(?:st|nd|rd|th)[\s,&]*)+)\s+"
    rf"({_MONTH_NAMES})",
    re.IGNORECASE,
)

# Extract individual day numbers from a days string like "29th 30th & 31st"
_DAY_RE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)")

_CONCURRENCY = 6


def _infer_year(month_num: int) -> int:
    """Infer the event year: if month is before current month, assume next year."""
    today = date.today()
    if month_num < today.month:
        return today.year + 1
    return today.year


@register_parser("outdoor_shows")
class OutdoorShowsParser(BaseParser):
    """Parser for outdoorshows.co.uk — steam rallies and country fairs.

    Discovers event URLs from sitemap (preferred) or homepage links (fallback),
    then scrapes each page for dates, venue, postcode.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        today = date.today()
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": "EquiCalendar/1.0"},
        ) as client:
            # Get event URLs from sitemap or homepage
            event_urls = await self._get_event_urls(client)
            logger.info("Outdoor Shows: %d event URLs discovered", len(event_urls))

            # Fetch all pages concurrently
            competitions = await self._fetch_all(client, event_urls, today)

        logger.info("Outdoor Shows: %d competitions extracted", len(competitions))
        return competitions

    async def _get_event_urls(self, client: httpx.AsyncClient) -> list[str]:
        """Discover event page URLs from sitemap (preferred) or homepage fallback."""
        # Try sitemap first
        urls = await self._get_urls_from_sitemap(client)
        if urls:
            return urls

        # Fallback: scrape homepage for event links
        logger.info("Outdoor Shows: sitemap unavailable, using homepage links")
        return await self._get_urls_from_homepage(client)

    async def _get_urls_from_sitemap(self, client: httpx.AsyncClient) -> list[str]:
        """Fetch sitemap and extract event page URLs."""
        try:
            resp = await client.get(SITEMAP_URL)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Outdoor Shows: sitemap fetch failed: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "xml")
        urls = []
        for loc in soup.find_all("loc"):
            url = loc.get_text(strip=True)
            path = url.replace(BASE_URL, "")
            if not path.endswith("/"):
                path += "/"
            if path not in _SKIP_SLUGS:
                urls.append(url)
        return urls

    async def _get_urls_from_homepage(self, client: httpx.AsyncClient) -> list[str]:
        """Scrape homepage for event page links."""
        try:
            resp = await client.get(BASE_URL + "/")
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Outdoor Shows: homepage fetch failed: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        seen: set[str] = set()
        urls: list[str] = []

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()

            # Skip pure anchors, images, mail, tel
            if href.startswith(("#", "mailto:", "tel:")):
                continue
            if re.search(r"\.(jpg|jpeg|png|gif|svg|webp|pdf)$", href, re.IGNORECASE):
                continue

            # Strip fragment identifiers before processing
            href = href.split("#")[0]
            if not href:
                continue

            # Normalise to absolute https URL
            if href.startswith("/"):
                href = BASE_URL + href
            elif href.startswith("http://outdoorshows"):
                href = href.replace("http://", "https://")

            # Must be on this domain
            if not href.startswith(BASE_URL):
                continue

            # Check slug against skip list
            path = href.replace(BASE_URL, "")
            if not path.endswith("/"):
                path += "/"
            if path in _SKIP_SLUGS:
                continue

            # Deduplicate
            canonical = href.rstrip("/")
            if canonical not in seen:
                seen.add(canonical)
                urls.append(href)

        return urls

    async def _fetch_all(
        self, client: httpx.AsyncClient, urls: list[str], today: date
    ) -> list[ExtractedCompetition]:
        """Fetch event pages concurrently."""
        sem = asyncio.Semaphore(_CONCURRENCY)

        async def fetch_one(url: str) -> ExtractedCompetition | None:
            async with sem:
                try:
                    return await self._parse_event_page(client, url, today)
                except Exception as e:
                    logger.debug("Outdoor Shows: failed to parse %s: %s", url, e)
                    return None

        tasks = [fetch_one(u) for u in urls]
        results = await asyncio.gather(*tasks)
        return [c for c in results if c is not None]

    async def _parse_event_page(
        self, client: httpx.AsyncClient, url: str, today: date
    ) -> ExtractedCompetition | None:
        """Parse a single event page."""
        resp = await client.get(url)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Name from <title>, strip " - Outdoor Shows"
        title_tag = soup.find("title")
        if not title_tag:
            return None
        name = title_tag.get_text(strip=True)
        name = re.sub(r"\s*[-–]\s*Outdoor Shows\s*$", "", name, flags=re.IGNORECASE)
        # Skip the homepage or generic site pages
        if not name or len(name) < 3 or "outdoor shows" in name.lower():
            return None

        # Extract hero text from wpb_wrapper divs (date + venue in first short one).
        # Using full page text picks up sidebar campsite dates instead of event dates.
        hero_text = self._extract_hero_text(soup)
        page_text = soup.get_text(" ", strip=True)

        # Dates — prefer hero text, fall back to full page
        date_start, date_end = self._extract_dates(hero_text)
        if not date_start:
            date_start, date_end = self._extract_dates(page_text)
        if not date_start:
            return None
        if not is_future_event(date_start, date_end):
            return None

        # Venue and postcode — prefer hero text, then LOCATION: pattern, then fallback
        venue_name, venue_postcode = self._extract_venue_from_hero(hero_text)
        if venue_name == "TBC":
            venue_name, venue_postcode = self._extract_venue(page_text)

        return ExtractedCompetition(
            name=name,
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name=venue_name,
            venue_postcode=venue_postcode,
            discipline="Agricultural Show",
            has_pony_classes=False,
            url=url,
        )

    def _extract_hero_text(self, soup: BeautifulSoup) -> str:
        """Extract the hero/header text from wpb_wrapper divs.

        Event pages use a short wpb_wrapper div as the hero banner containing
        the date and venue, e.g. "29th 30th & 31st August Belvoir Castle, Grantham, NG32 1PA".
        """
        for div in soup.find_all("div", class_=re.compile(r"wpb_wrapper")):
            text = div.get_text(" ", strip=True)
            # Hero div is short and contains a month name
            if 10 < len(text) < 200 and re.search(rf"\b({_MONTH_NAMES})\b", text, re.IGNORECASE):
                return text
        return ""

    def _extract_venue_from_hero(self, hero_text: str) -> tuple[str, str | None]:
        """Extract venue from hero text like '29th & 30th August Venue Name, Town, POSTCODE'.

        For cross-month dates like '31st July 1st & 2nd August Venue...',
        strips up to the last month name in the date pattern.
        """
        if not hero_text:
            return "TBC", None

        postcode = extract_postcode(hero_text)

        # Strip the date portion up to the LAST month name
        # This handles cross-month: "31st July 1st & 2nd August Venue..."
        venue_part = re.sub(
            rf"^(?:.*\b({_MONTH_NAMES})\b)\s*",
            "",
            hero_text,
            flags=re.IGNORECASE,
        ).strip()

        if not venue_part:
            return "TBC", postcode

        # Remove postcode from venue name
        if postcode:
            idx = venue_part.upper().find(postcode.upper())
            if idx >= 0:
                venue_part = venue_part[:idx].rstrip(" ,.-")

        return venue_part.strip() or "TBC", postcode

    def _extract_dates(self, text: str) -> tuple[str | None, str | None]:
        """Extract start and end dates from page text."""
        # Try cross-month first: "31st July 1st & 2nd August"
        m = _DATES_CROSS_MONTH_RE.search(text)
        if m:
            start_day = int(m.group(1))
            start_month = _MONTH_MAP.get(m.group(2).lower())
            end_days_str = m.group(3)
            end_month = _MONTH_MAP.get(m.group(4).lower())
            if start_month and end_month:
                end_days = [int(d) for d in _DAY_RE.findall(end_days_str)]
                year = _infer_year(start_month)
                try:
                    start = date(year, start_month, start_day).isoformat()
                    end_day = max(end_days) if end_days else start_day
                    end = date(year, end_month, end_day).isoformat()
                    return start, end
                except ValueError:
                    pass

        # Try single-month dates: "5th & 6th September"
        m = _DATES_SINGLE_MONTH_RE.search(text)
        if m:
            days_str = m.group(1)
            month = _MONTH_MAP.get(m.group(2).lower())
            if month:
                days = [int(d) for d in _DAY_RE.findall(days_str)]
                if days:
                    year = _infer_year(month)
                    try:
                        start = date(year, month, min(days)).isoformat()
                        end = date(year, month, max(days)).isoformat() if len(days) > 1 else None
                        return start, end
                    except ValueError:
                        pass

        return None, None

    def _extract_venue(self, text: str) -> tuple[str, str | None]:
        """Extract venue name and postcode from page text."""
        postcode = extract_postcode(text)

        # Try "LOCATION:" pattern
        loc_match = re.search(
            r"LOCATION:\s*(.+?)(?:\n|\r|ADMISSION|TICKET|BUY|OPENING|CAMPING|INTRODUCTION|$)",
            text,
            re.IGNORECASE,
        )
        if loc_match:
            loc_text = loc_match.group(1).strip()
            # Remove postcode from venue name
            if postcode:
                venue = loc_text[:loc_text.upper().find(postcode.upper())].rstrip(" ,.-")
            else:
                venue = loc_text
            if venue:
                return venue, postcode

        # Fallback: extract text around the postcode
        if postcode:
            idx = text.upper().find(postcode.upper())
            if idx > 0:
                # Take up to 100 chars before postcode
                before = text[max(0, idx - 100):idx].strip()
                # Find the last sentence/line boundary
                for sep in ["\n", ". ", "  "]:
                    last_sep = before.rfind(sep)
                    if last_sep >= 0:
                        before = before[last_sep:].strip(". \n")
                        break
                if before:
                    return before.rstrip(" ,.-"), postcode

        return "TBC", postcode
