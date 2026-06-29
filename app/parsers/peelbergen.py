from __future__ import annotations

import html as html_mod
import re

from app.parsers.bases import TribeEventsParser
from app.parsers.registry import register_parser
from app.parsers.utils import continental_discipline, continental_event_type, prefix_venue
from app.schemas import ExtractedEvent


@register_parser("peelbergen")
class PeelbergenParser(TribeEventsParser):
    """Peelbergen Equestrian Centre (NL) — WordPress + The Events Calendar REST API.

    A large multi-ring venue: one schedule spans enterable youth/amateur classes
    (CSI1*/YH, PRO Tour, talent search) up to elite internationals (CSIO3*+).
    ``event_type`` is decided per event so enterable classes land in Compete (and
    Watch when starred) while pure-elite fixtures stay Watch-only.
    """

    VENUE_NAME = "Peelbergen Equestrian Centre"
    VENUE_POSTCODE = None
    BASE_URL = "https://www.peelbergen.eu"
    LABEL = "Peelbergen"
    LAT = 51.364
    LNG = 6.11

    def _parse_tribe_event(self, event: dict) -> ExtractedEvent | None:
        name = html_mod.unescape(event.get("title", "")).strip()
        if not name:
            return None
        date_start = (event.get("start_date") or "")[:10]
        if not re.match(r"\d{4}-\d{2}-\d{2}", date_start):
            return None
        date_end = (event.get("end_date") or "")[:10]
        if date_end == date_start:
            date_end = None
        return self._build_event(
            name=prefix_venue(name, self.LABEL),
            date_start=date_start,
            date_end=date_end,
            latitude=self.LAT,
            longitude=self.LNG,
            discipline=continental_discipline(name),
            event_type=continental_event_type(name),
            url=event.get("url", f"{self.BASE_URL}/events/"),
        )
