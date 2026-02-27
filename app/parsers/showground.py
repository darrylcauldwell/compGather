from __future__ import annotations

import html
import logging
import re
from datetime import date, datetime

from app.parsers.bases import BROWSER_UA, SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

SHOW_PAGES = ["/walesandwestshows", "/cricklands"]

_DATE_RANGE_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s*-\s*(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)",
    re.IGNORECASE,
)


@register_parser("showground")
class ShowgroundParser(SingleVenueParser):
    """Parser for theshowground.com — Wix site, HTML scraping.

    Single venue: Mount Ballan Manor, Crick, Nr Chepstow (NP26 5XP).
    """

    VENUE_NAME = "The Showground"
    VENUE_POSTCODE = "NP26 5XP"
    BASE_URL = "https://www.theshowground.com"
    HEADERS = {"User-Agent": BROWSER_UA}

    VENUE_LAT = 51.5991
    VENUE_LNG = -2.735797

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        competitions: list[ExtractedEvent] = []

        async with self._make_client() as client:
            for page_path in SHOW_PAGES:
                try:
                    text = await self._fetch_text(client, f"{self.BASE_URL}{page_path}")
                    competitions.extend(self._extract_shows(text, page_path))
                except Exception as e:
                    logger.warning("Showground: failed to fetch %s: %s", page_path, e)

        self._log_result("Showground", len(competitions))
        return competitions

    def _extract_shows(self, page_html, page_path):
        competitions = []
        seen: set[str] = set()

        for date_match in _DATE_RANGE_RE.finditer(page_html):
            start_day = int(date_match.group(1))
            end_day = int(date_match.group(2))
            month_name = date_match.group(3)

            search_start = max(0, date_match.start() - 500)
            before = page_html[search_start:date_match.start()]
            titles = re.findall(r'class="wixui-rich-text__text">([^<]{3,})<', before)
            if not titles:
                continue
            title = html.unescape(titles[-1].strip())

            year = self._infer_year(month_name)
            try:
                ds = datetime.strptime(f"{start_day} {month_name} {year}", "%d %B %Y").date()
                de = datetime.strptime(f"{end_day} {month_name} {year}", "%d %B %Y").date()
            except ValueError:
                continue

            key = f"{title}|{ds.isoformat()}"
            if key in seen:
                continue
            seen.add(key)

            competitions.append(self._build_event(
                name=title,
                date_start=ds.isoformat(),
                date_end=de.isoformat() if de != ds else None,
                latitude=self.VENUE_LAT,
                longitude=self.VENUE_LNG,
                url=self._build_detail_url(title, page_path),
            ))

        return competitions

    def _infer_year(self, month_name):
        today = date.today()
        month_num = datetime.strptime(month_name, "%B").month
        return today.year + 1 if month_num < today.month else today.year

    def _build_detail_url(self, title, page_path):
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
        return f"{self.BASE_URL}{slug}" if slug else f"{self.BASE_URL}{page_path}"
