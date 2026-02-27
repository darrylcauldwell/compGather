from __future__ import annotations

import logging
import re

from app.parsers.bases import BROWSER_UA, SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

_DTSTART_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})T")


@register_parser("port_royal")
class PortRoyalParser(SingleVenueParser):
    """Parser for portroyaleec.co.uk — SilverStripe CMS, HTML scraping.

    Single venue: Port Royal Equestrian and Show Centre (YO43 4AZ).
    """

    VENUE_NAME = "Port Royal"
    VENUE_POSTCODE = "YO43 4AZ"
    BASE_URL = "https://www.portroyaleec.co.uk"
    HEADERS = {"User-Agent": BROWSER_UA}

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        async with self._make_client() as client:
            soup = await self._fetch_html(client, f"{self.BASE_URL}/calender/")

        competitions: list[ExtractedEvent] = []

        events_div = soup.select_one("div#events")
        if not events_div:
            logger.warning("Port Royal: no div#events found")
            return []

        for li in events_div.select("ul > li"):
            if "head" in li.get("class", []):
                continue

            title_link = li.select_one("h2 a")
            if not title_link:
                continue
            title = title_link.get_text(strip=True)

            dtstart = li.select_one("span.dtstart")
            if dtstart:
                date_start = self._parse_dtstart(dtstart.get("title", ""))
                if date_start:
                    competitions.append(self._build_event(
                        name=title,
                        date_start=date_start,
                        discipline=None,
                        url=self._abs_url(title_link.get("href", "")),
                    ))

            for also_link in li.select("h3 ~ ul a"):
                also_dtstart = also_link.select_one("span.dtstart")
                if also_dtstart:
                    also_date = self._parse_dtstart(also_dtstart.get("title", ""))
                    if also_date:
                        competitions.append(self._build_event(
                            name=title,
                            date_start=also_date,
                            discipline=None,
                            url=self._abs_url(also_link.get("href", "")),
                        ))

        competitions = self._dedup(competitions)
        self._log_result("Port Royal", len(competitions))
        return competitions

    def _parse_dtstart(self, title: str) -> str | None:
        m = _DTSTART_RE.match(title)
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None

    def _abs_url(self, href: str) -> str:
        return href if href.startswith("http") else f"{self.BASE_URL}{href}"
