from __future__ import annotations

import logging

from app.parsers.bases import HttpParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

# Full 2026 LGCT tour calendar — update annually
_LGCT_2026_STOPS: list[dict] = [
    {
        "name": "LGCT Doha 2026",
        "venue_name": "Al Shaqab",
        "date_start": "2026-03-04",
        "date_end": "2026-03-07",
        "latitude": 25.3178,
        "longitude": 51.4286,
    },
    {
        "name": "LGCT Miami Beach 2026",
        "venue_name": "Miami Beach",
        "date_start": "2026-04-03",
        "date_end": "2026-04-05",
        "latitude": 25.7907,
        "longitude": -80.1300,
    },
    {
        "name": "LGCT Mexico City 2026",
        "venue_name": "Campo Marte",
        "date_start": "2026-04-16",
        "date_end": "2026-04-19",
        "latitude": 19.4326,
        "longitude": -99.1332,
    },
    {
        "name": "LGCT Shanghai 2026",
        "venue_name": "Shanghai",
        "date_start": "2026-05-01",
        "date_end": "2026-05-03",
        "latitude": 31.2304,
        "longitude": 121.4737,
    },
    {
        "name": "LGCT Madrid 2026",
        "venue_name": "Club de Campo Villa de Madrid",
        "date_start": "2026-05-15",
        "date_end": "2026-05-17",
        "latitude": 40.4378,
        "longitude": -3.7495,
    },
    {
        "name": "LGCT Cannes 2026",
        "venue_name": "Cannes",
        "date_start": "2026-06-04",
        "date_end": "2026-06-06",
        "latitude": 43.5528,
        "longitude": 7.0174,
    },
    {
        "name": "LGCT St Tropez 2026",
        "venue_name": "Ramatuelle",
        "date_start": "2026-06-11",
        "date_end": "2026-06-13",
        "latitude": 43.2185,
        "longitude": 6.6110,
    },
    {
        "name": "LGCT Paris 2026",
        "venue_name": "Champ de Mars, Paris",
        "date_start": "2026-06-19",
        "date_end": "2026-06-21",
        "latitude": 48.8566,
        "longitude": 2.2945,
    },
    {
        "name": "LGCT Monaco 2026",
        "venue_name": "Port Hercule, Monaco",
        "date_start": "2026-07-02",
        "date_end": "2026-07-04",
        "latitude": 43.7384,
        "longitude": 7.4246,
    },
    {
        "name": "LGCT Riesenbeck 2026",
        "venue_name": "Riesenbeck International",
        "date_start": "2026-07-16",
        "date_end": "2026-07-19",
        "latitude": 52.2733,
        "longitude": 7.6500,
    },
    {
        "name": "LGCT London 2026",
        "venue_name": "Royal Hospital Chelsea",
        "venue_postcode": "SW3 4SR",
        "date_start": "2026-08-07",
        "date_end": "2026-08-09",
        "latitude": 51.4883,
        "longitude": -0.1579,
    },
    {
        "name": "LGCT Valkenswaard 2026",
        "venue_name": "Tops International Arena",
        "date_start": "2026-09-04",
        "date_end": "2026-09-06",
        "latitude": 51.3512,
        "longitude": 5.4614,
    },
    {
        "name": "LGCT Vienna 2026",
        "venue_name": "Vienna",
        "date_start": "2026-09-24",
        "date_end": "2026-09-27",
        "latitude": 48.2082,
        "longitude": 16.3738,
    },
    {
        "name": "LGCT Rome 2026",
        "venue_name": "Rome",
        "date_start": "2026-10-09",
        "date_end": "2026-10-11",
        "latitude": 41.9028,
        "longitude": 12.4964,
    },
    {
        "name": "LGCT Cairo 2026",
        "venue_name": "Cairo",
        "date_start": "2026-10-22",
        "date_end": "2026-10-24",
        "latitude": 30.0444,
        "longitude": 31.2357,
    },
    {
        "name": "LGCT Rabat 2026",
        "venue_name": "Rabat",
        "date_start": "2026-10-30",
        "date_end": "2026-11-01",
        "latitude": 34.0209,
        "longitude": -6.8416,
    },
    {
        "name": "LGCT Riyadh 2026",
        "venue_name": "Riyadh",
        "date_start": "2026-11-18",
        "date_end": "2026-11-21",
        "latitude": 24.7136,
        "longitude": 46.6753,
    },
]


@register_parser("lgct")
class LGCTParser(HttpParser):
    """Parser for the Longines Global Champions Tour — international show jumping series.

    Static parser: the full 2026 tour calendar is hard-coded.
    Returns one event per tour stop (17 stops across 15 countries).
    """

    BASE_URL = "https://www.gcglobalchampions.com"
    HEADERS = {"User-Agent": "EquiCalendar/1.0"}

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("LGCT: site unreachable, returning static data")

        events = []
        for stop in _LGCT_2026_STOPS:
            events.append(
                self._build_event(
                    name=stop["name"],
                    date_start=stop["date_start"],
                    date_end=stop["date_end"],
                    venue_name=stop["venue_name"],
                    venue_postcode=stop.get("venue_postcode"),
                    latitude=stop.get("latitude"),
                    longitude=stop.get("longitude"),
                    discipline="Show Jumping",
                    event_type="show",
                    url=url,
                )
            )

        self._log_result("LGCT", len(events))
        return events
