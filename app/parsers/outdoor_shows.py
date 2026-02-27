from __future__ import annotations

import logging
import re
from datetime import date

from bs4 import BeautifulSoup

from app.parsers.bases import TwoPhaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import extract_postcode
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://outdoorshows.co.uk/page-sitemap.xml"
BASE_URL = "https://outdoorshows.co.uk"

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

_DATES_SINGLE_MONTH_RE = re.compile(
    r"((?:\d{1,2}(?:st|nd|rd|th)[\s,&]*)+)\s+"
    rf"({_MONTH_NAMES})",
    re.IGNORECASE,
)

_DATES_CROSS_MONTH_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)\s+"
    rf"({_MONTH_NAMES})\s+"
    r"((?:\d{1,2}(?:st|nd|rd|th)[\s,&]*)+)\s+"
    rf"({_MONTH_NAMES})",
    re.IGNORECASE,
)

_DAY_RE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)")


def _infer_year(month_num):
    today = date.today()
    return today.year + 1 if month_num < today.month else today.year


@register_parser("outdoor_shows")
class OutdoorShowsParser(TwoPhaseParser):
    """Parser for outdoorshows.co.uk — steam rallies and country fairs.

    Discovers event URLs from sitemap (preferred) or homepage links (fallback),
    then scrapes each page for dates, venue, postcode.
    """

    CONCURRENCY = 6

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        today = date.today()
        async with self._make_client() as client:
            event_urls = await self._get_event_urls(client)
            logger.info("Outdoor Shows: %d event URLs discovered", len(event_urls))

            competitions = await self._concurrent_fetch(
                event_urls,
                lambda u: self._parse_event_page(client, u, today),
            )

        self._log_result("Outdoor Shows", len(competitions))
        return competitions

    async def _get_event_urls(self, client):
        urls = await self._get_urls_from_sitemap(client)
        if urls:
            return urls
        logger.info("Outdoor Shows: sitemap unavailable, using homepage links")
        return await self._get_urls_from_homepage(client)

    async def _get_urls_from_sitemap(self, client):
        try:
            resp = await client.get(SITEMAP_URL)
            resp.raise_for_status()
        except Exception as e:
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

    async def _get_urls_from_homepage(self, client):
        try:
            resp = await client.get(BASE_URL + "/")
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Outdoor Shows: homepage fetch failed: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        seen: set[str] = set()
        urls: list[str] = []

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("#", "mailto:", "tel:")):
                continue
            if re.search(r"\.(jpg|jpeg|png|gif|svg|webp|pdf)$", href, re.IGNORECASE):
                continue

            href = href.split("#")[0]
            if not href:
                continue

            if href.startswith("/"):
                href = BASE_URL + href
            elif href.startswith("http://outdoorshows"):
                href = href.replace("http://", "https://")

            if not href.startswith(BASE_URL):
                continue

            path = href.replace(BASE_URL, "")
            if not path.endswith("/"):
                path += "/"
            if path in _SKIP_SLUGS:
                continue

            canonical = href.rstrip("/")
            if canonical not in seen:
                seen.add(canonical)
                urls.append(href)

        return urls

    async def _parse_event_page(self, client, url, today):
        resp = await client.get(url)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        title_tag = soup.find("title")
        if not title_tag:
            return None
        name = title_tag.get_text(strip=True)
        name = re.sub(r"\s*[-–]\s*Outdoor Shows\s*$", "", name, flags=re.IGNORECASE)
        if not name or len(name) < 3 or "outdoor shows" in name.lower():
            return None

        hero_text = self._extract_hero_text(soup)
        page_text = soup.get_text(" ", strip=True)

        date_start, date_end = self._extract_dates(hero_text)
        if not date_start:
            date_start, date_end = self._extract_dates(page_text)
        if not date_start:
            return None

        venue_name, venue_postcode = self._extract_venue_from_hero(hero_text)
        if venue_name == "TBC":
            venue_name, venue_postcode = self._extract_venue(page_text)

        return self._build_event(
            name=name,
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name=venue_name,
            venue_postcode=venue_postcode,
            discipline="Agricultural Show",
            url=url,
        )

    def _extract_hero_text(self, soup):
        for div in soup.find_all("div", class_=re.compile(r"wpb_wrapper")):
            text = div.get_text(" ", strip=True)
            if 10 < len(text) < 200 and re.search(rf"\b({_MONTH_NAMES})\b", text, re.IGNORECASE):
                return text
        return ""

    def _extract_venue_from_hero(self, hero_text):
        if not hero_text:
            return "TBC", None

        postcode = extract_postcode(hero_text)
        venue_part = re.sub(
            rf"^(?:.*\b({_MONTH_NAMES})\b)\s*", "", hero_text, flags=re.IGNORECASE,
        ).strip()

        if not venue_part:
            return "TBC", postcode

        if postcode:
            idx = venue_part.upper().find(postcode.upper())
            if idx >= 0:
                venue_part = venue_part[:idx].rstrip(" ,.-")

        return venue_part.strip() or "TBC", postcode

    def _extract_dates(self, text):
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

    def _extract_venue(self, text):
        postcode = extract_postcode(text)
        loc_match = re.search(
            r"LOCATION:\s*(.+?)(?:\n|\r|ADMISSION|TICKET|BUY|OPENING|CAMPING|INTRODUCTION|$)",
            text, re.IGNORECASE,
        )
        if loc_match:
            loc_text = loc_match.group(1).strip()
            if postcode:
                venue = loc_text[:loc_text.upper().find(postcode.upper())].rstrip(" ,.-")
            else:
                venue = loc_text
            if venue:
                return venue, postcode

        if postcode:
            idx = text.upper().find(postcode.upper())
            if idx > 0:
                before = text[max(0, idx - 100):idx].strip()
                for sep in ["\n", ". ", "  "]:
                    last_sep = before.rfind(sep)
                    if last_sep >= 0:
                        before = before[last_sep:].strip(". \n")
                        break
                if before:
                    return before.rstrip(" ,.-"), postcode

        return "TBC", postcode
