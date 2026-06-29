from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.parsers.utils import continental_discipline, continental_event_type, prefix_venue
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("azelhof")
class AzelhofParser(SingleVenueParser):
    """Azelhof (Lier, BE) — static HTML events table at /en/events.

    Columns: Soort (type) | Begin | Eind | Event | register | read more.
    Weekly ``TRAININGSJUMPING`` rows (Soort == "Training") are schooling, not
    competitions, and are skipped. Tour weeks (CSI2*/1*/YH) are enterable +
    watchable; event_type is decided per row.
    """

    VENUE_NAME = "Azelhof"
    VENUE_POSTCODE = None
    BASE_URL = "https://azelhof.be"
    EVENTS_URL = "https://azelhof.be/en/events"
    LABEL = "Azelhof"
    LAT = 51.131
    LNG = 4.57

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        async with self._make_client() as client:
            soup = await self._fetch_html(client, self.EVENTS_URL)

        events: list[ExtractedEvent] = []
        table = soup.find("table", class_="table-events") or soup.find("table")
        if not table:
            self._log_result("Azelhof", 0)
            return events

        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 4:
                continue  # header / spacer row
            soort = cells[0].get_text(strip=True)
            if soort.lower() == "training":
                continue  # weekly schooling, not a competition
            name = cells[3].get_text(" ", strip=True)
            date_start = self._parse_date(cells[1].get_text(strip=True), ["%d %b %Y"])
            if not name or not date_start:
                continue
            date_end = self._parse_date(cells[2].get_text(strip=True), ["%d %b %Y"])

            link = tr.find("a", href=True)
            href = link["href"].strip() if link else self.EVENTS_URL
            if not href.startswith("http") or href.rstrip("/") in ("http:", "https:"):
                href = self.EVENTS_URL

            events.append(
                self._build_event(
                    name=prefix_venue(name, self.LABEL),
                    date_start=date_start,
                    date_end=date_end,
                    latitude=self.LAT,
                    longitude=self.LNG,
                    discipline=continental_discipline(name),
                    event_type=continental_event_type(name),
                    url=href,
                )
            )

        events = self._dedup(events)
        self._log_result("Azelhof", len(events))
        return events
