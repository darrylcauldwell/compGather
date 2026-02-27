from __future__ import annotations

import logging

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("sunshine_tour")
class SunshineTourParser(SingleVenueParser):
    """Parser for the Andalucia Sunshine Tour — Montenmedio, Vejer de la Frontera, Spain.

    Major international show jumping circuit running Feb-Mar each year.
    Fetches weekly competition schedule from the tour's JSON API.
    """

    VENUE_NAME = "Montenmedio"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.sunshinetour.net"

    TOUR_ID = "48606738"
    TOUR_JSON_URL = f"https://www.sunshinetour.net/assets/results/{TOUR_ID}/db.tour.{TOUR_ID}.json"

    # Static fallback if JSON fetch fails
    SHOW_NAME = "Andalucia Sunshine Tour 2026"
    DATE_START = "2026-02-02"
    DATE_END = "2026-03-22"

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                data = await self._fetch_json(client, self.TOUR_JSON_URL)

            events = []
            for week in data["payload"]["show_ids"]:
                week_code = week["virtual_week_code"]
                description = week["description"]
                name = f"Sunshine Tour {week_code} — {description}"

                events.append(
                    self._build_event(
                        name=name,
                        date_start=week["start_at"],
                        date_end=week["end_at"],
                        discipline="Show Jumping",
                        event_type="competition",
                        latitude=36.2519,
                        longitude=-5.8686,
                        url=self.BASE_URL,
                    )
                )

            events.sort(key=lambda e: e.date_start)
            self._log_result("Sunshine Tour", len(events))
            return events

        except Exception:
            logger.warning("Sunshine Tour: JSON fetch failed, returning static fallback")
            events = [
                self._build_event(
                    name=self.SHOW_NAME,
                    date_start=self.DATE_START,
                    date_end=self.DATE_END,
                    discipline="Show Jumping",
                    event_type="competition",
                    latitude=36.2519,
                    longitude=-5.8686,
                    url=url,
                )
            ]
            self._log_result("Sunshine Tour", len(events))
            return events
