from __future__ import annotations

import logging
import re
from datetime import date as date_cls

from bs4 import BeautifulSoup

from app.parsers.bases import PlaywrightParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

_MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        [
            "January", "February", "March", "April", "May", "June", "July",
            "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}
_MRE = "|".join(_MONTHS)
# "4 - 7 March" (same month) OR "30 October - 1 November" (crosses a month)
_DATE_RE = re.compile(
    rf"(?:(\d{{1,2}})\s*[–-]\s*(\d{{1,2}})\s+({_MRE}))"
    rf"|(?:(\d{{1,2}})\s+({_MRE})\s*[–-]\s*(\d{{1,2}})\s+({_MRE}))",
    re.IGNORECASE,
)
# Tokens that terminate a city name in the rendered grid text.
_STOP = {
    "tickets", "event", "guide", "city", "location", "start", "lists",
    "results", "schedule", "my", "and", "the", "faq", "venue",
}


@register_parser("gc_global_champions")
class GCGlobalChampionsParser(PlaywrightParser):
    """Longines Global Champions Tour / GCL — gcglobalchampions.com/schedule.

    A Next.js SPA: the season grid renders client-side, so Playwright is required
    (``networkidle`` never fires on this page — use ``domcontentloaded`` + a
    settle). It's a multi-venue circuit (one CSI5* leg per world city); every leg
    is an elite spectator fixture → ``event_type="show"`` (Watch-only).

    Marquee legs expose a city page (``/schedule/2026/<slug>/…``) giving a clean
    city name; the rest render as a plain "DD - DD Month City Tickets" list. The
    Riesenbeck leg is skipped — the dedicated Riesenbeck venue parser owns it.
    """

    WAIT_STRATEGY = "domcontentloaded"
    EXTRA_WAIT_MS = 7000
    TIMEOUT_MS = 45000

    BASE_URL = "https://www.gcglobalchampions.com"
    SEASON = 2026
    SKIP_CITIES = ("riesenbeck",)

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        html = await self._render_page(f"{self.BASE_URL}/schedule")
        if not html:
            logger.warning("GC Global Champions: no rendered HTML (Playwright?)")
            return []
        return self._parse(html)

    def _parse(self, html: str) -> list[ExtractedEvent]:
        """Extract circuit legs from the rendered schedule HTML (no network)."""
        soup = BeautifulSoup(html, "html.parser")

        # Legs with a city page → clean slug name, keyed by start date.
        link_by_date: dict[str, tuple[str, str]] = {}
        for a in soup.find_all("a", href=True):
            m = re.search(rf"/schedule/{self.SEASON}/([a-z][a-z\-]+)", a["href"])
            if not m or m.group(1) == "faq":
                continue
            el = a
            for _ in range(7):
                if el.parent:
                    el = el.parent
                dm = _DATE_RE.search(el.get_text(" ", strip=True))
                if dm:
                    ds, _ = self._range_iso(dm)
                    if ds:
                        link_by_date.setdefault(ds, (m.group(1), a["href"]))
                    break

        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
        events: list[ExtractedEvent] = []
        seen: set[str] = set()
        for dm in _DATE_RE.finditer(text):
            ds, de = self._range_iso(dm)
            if not ds or ds in seen:
                continue

            link = link_by_date.get(ds)
            if link:
                slug, href = link
                city = slug.replace("-", " ").title()
                event_url = self.BASE_URL + href
            else:
                city = self._city_from_text(text[dm.end():dm.end() + 60])
                event_url = f"{self.BASE_URL}/schedule"

            if not city or any(s in city.lower() for s in self.SKIP_CITIES):
                continue

            seen.add(ds)
            events.append(
                self._build_event(
                    name=f"Longines Global Champions Tour — {city}",
                    date_start=ds,
                    date_end=de if de != ds else None,
                    venue_name=city,
                    discipline="Show Jumping",
                    event_type="show",
                    url=event_url,
                )
            )

        events.sort(key=lambda e: e.date_start)
        self._log_result("GC Global Champions", len(events))
        return events

    def _range_iso(self, m: re.Match) -> tuple[str | None, str | None]:
        g = m.groups()
        try:
            if g[0]:  # same month: DD - DD Month
                mo = _MONTHS[g[2].lower()]
                start = date_cls(self.SEASON, mo, int(g[0]))
                end = date_cls(self.SEASON, mo, int(g[1]))
            else:  # cross month: DD Month - DD Month
                start = date_cls(self.SEASON, _MONTHS[g[4].lower()], int(g[3]))
                end = date_cls(self.SEASON, _MONTHS[g[6].lower()], int(g[5]))
        except (ValueError, KeyError, TypeError):
            return None, None
        return start.isoformat(), end.isoformat()

    @staticmethod
    def _city_from_text(follow: str) -> str:
        words: list[str] = []
        for w in follow.split():
            if w[:1].isdigit():
                break
            token = re.sub(r"[^\w&]", "", w).lower()
            if not token or token in _STOP:
                break
            words.append(w)
            if len(words) >= 4:
                break
        return " ".join(words).strip(" ,.")
