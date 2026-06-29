from __future__ import annotations

import logging
import re
from datetime import date as date_cls

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.parsers.utils import continental_discipline, continental_event_type
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

_IT_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5,
    "giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10,
    "novembre": 11, "dicembre": 12,
}
_EN_MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}
# "26.27.28 GIUGNO 2026  Nazionale A5* ..."
_LINE_RE = re.compile(
    r"^([\d.\s]+?)\s+(" + "|".join(_IT_MONTHS) + r")\s+(20\d\d)\b\s*(.*)$",
    re.IGNORECASE,
)
_GRADE_RE = re.compile(r"(Nazionale\s+[A-Z]?\d\*?|CSI\d?\*?|CDN\w*|Internazionale)", re.IGNORECASE)


@register_parser("le_siepi")
class LeSiepiParser(SingleVenueParser):
    """Circolo Ippico Le Siepi (Cervia, IT) — Adriatic Tour, free-text /concorsi/ page.

    The competitions page has no semantic markup: each fixture is a paragraph
    like "26.27.28 GIUGNO 2026 Nazionale A5* Montepremi …". We regex the date
    range (Italian months) and grade, and use the listing page as the link
    (there are no per-event URLs).
    """

    VENUE_NAME = "Circolo Ippico Le Siepi"
    VENUE_POSTCODE = None
    BASE_URL = "https://lesiepicervia.it"
    EVENTS_URL = "https://lesiepicervia.it/concorsi/"
    LAT = 44.268
    LNG = 12.355

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        async with self._make_client() as client:
            soup = await self._fetch_html(client, self.EVENTS_URL)

        events: list[ExtractedEvent] = []
        seen: set[tuple] = set()
        for el in soup.find_all(["p", "div", "span", "strong", "h2", "h3", "h4", "li"]):
            text = el.get_text(" ", strip=True).replace("\xa0", " ")
            m = _LINE_RE.match(text)
            if not m:
                continue
            days_blob, month_it, year_s, rest = m.groups()
            month = _IT_MONTHS.get(month_it.lower())
            days = [int(d) for d in re.findall(r"\d{1,2}", days_blob)]
            if not month or not days:
                continue

            year = int(year_s)
            try:
                start = date_cls(year, month, days[0])
                end = date_cls(year, month, days[-1])
            except ValueError:
                continue

            grade_m = _GRADE_RE.search(rest)
            if not grade_m:
                continue  # date-only header (e.g. a bare <strong>), not a fixture
            grade = grade_m.group(1).strip()
            span = (
                f"{days[0]}–{days[-1]} {_EN_MONTH_ABBR[month]}"
                if days[-1] != days[0]
                else f"{days[0]} {_EN_MONTH_ABBR[month]}"
            )
            name = f"Adriatic Tour — {grade} ({span})"

            key = (start.isoformat(), grade.lower())
            if key in seen:
                continue
            seen.add(key)

            ds = start.isoformat()
            de = end.isoformat()
            events.append(
                self._build_event(
                    name=name,
                    date_start=ds,
                    date_end=de if de != ds else None,
                    latitude=self.LAT,
                    longitude=self.LNG,
                    discipline=continental_discipline(grade),
                    event_type=continental_event_type(grade),
                    url=self.EVENTS_URL,
                )
            )

        events.sort(key=lambda e: e.date_start)
        self._log_result("Le Siepi", len(events))
        return events
