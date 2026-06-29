from __future__ import annotations

import logging
import re
from datetime import date as date_cls

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.parsers.utils import continental_discipline, continental_event_type, prefix_venue
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january", "february", "march", "april", "may", "june", "july",
            "august", "september", "october", "november", "december",
        ],
        start=1,
    )
}
_MONTH_RE = "|".join(_MONTHS)


@register_parser("riesenbeck")
class RiesenbeckParser(SingleVenueParser):
    """Riesenbeck International (DE) — static HTML event cards at /en/events/.

    Each ``article.event-list-item__box`` carries a date-range prefix
    ("16.- 19. July 2026") followed by the title. Home of the Longines Global
    Champions Tour (elite, Watch-only) plus CSI** fixtures.
    """

    VENUE_NAME = "Riesenbeck International"
    VENUE_POSTCODE = None
    BASE_URL = "https://riesenbeck-international.com"
    EVENTS_URL = "https://riesenbeck-international.com/en/events/"
    LABEL = "Riesenbeck"
    LAT = 52.253
    LNG = 7.5974
    SKIP = ("summer camp", "late entry")

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        async with self._make_client() as client:
            soup = await self._fetch_html(client, self.EVENTS_URL)

        events: list[ExtractedEvent] = []
        for art in soup.find_all("article", class_="event-list-item__box"):
            heading = art.find(["h1", "h2", "h3"])
            if not heading:
                continue
            title = heading.get_text(" ", strip=True)
            if any(s in title.lower() for s in self.SKIP):
                continue

            full = art.get_text(" ", strip=True).replace("\xa0", " ")
            date_part = full[: full.find(title)] if title in full else full
            date_start, date_end = self._parse_range(date_part)
            if not date_start:
                continue

            link = art.find("a", href=True)
            href = link["href"] if link else self.EVENTS_URL
            if href.startswith("/"):
                href = self.BASE_URL + href

            clean = self._clean_title(title)
            events.append(
                self._build_event(
                    name=prefix_venue(clean, self.LABEL),
                    date_start=date_start,
                    date_end=date_end,
                    latitude=self.LAT,
                    longitude=self.LNG,
                    discipline=continental_discipline(clean),
                    event_type=continental_event_type(clean),
                    url=href,
                )
            )

        events = self._dedup(events)
        self._log_result("Riesenbeck International", len(events))
        return events

    def _parse_range(self, text: str) -> tuple[str | None, str | None]:
        """Parse "16.- 19. July 2026" / "30. September - 3. October 2026" / "4. July 2026"."""
        text = text.replace("\xa0", " ")
        year_m = re.search(r"(20\d\d)", text)
        months = re.findall(_MONTH_RE, text, re.IGNORECASE)
        days = re.findall(r"(\d{1,2})\.", text)
        if not year_m or not months or not days:
            return None, None

        year = int(year_m.group(1))
        start_month = _MONTHS[months[0].lower()]
        start_day = int(days[0])
        if len(months) >= 2:  # crosses a month boundary
            end_month = _MONTHS[months[1].lower()]
            end_day = int(days[-1])
        else:
            end_month = start_month
            end_day = int(days[-1]) if len(days) >= 2 else start_day

        try:
            start = date_cls(year, start_month, start_day)
            end_year = year + 1 if end_month < start_month else year
            end = date_cls(end_year, end_month, end_day)
        except ValueError:
            return None, None

        ds = start.isoformat()
        de = end.isoformat()
        return ds, (de if de != ds else None)

    @staticmethod
    def _clean_title(title: str) -> str:
        """Strip a date fragment some titles embed ("CSI** 30. September - 03. October")."""
        t = re.sub(r"\b\d{1,2}\.\s*", "", title)
        t = re.sub(_MONTH_RE, "", t, flags=re.IGNORECASE)
        t = re.sub(r"\b20\d\d\b", "", t)
        t = re.sub(r"\s*[-–]\s*", " ", t)
        t = re.sub(r"\s{2,}", " ", t).strip(" -–.")
        return t or title.strip()
