from __future__ import annotations

from app.parsers.bases import BROWSER_UA, TribeEventsParser
from app.parsers.registry import register_parser


@register_parser("morris")
class MorrisParser(TribeEventsParser):
    """Parser for morrisequestrian.co.uk — Tribe Events Calendar REST API.

    All events are at Morris Equestrian Centre (KA3 6AY).
    """

    VENUE_NAME = "Morris"
    VENUE_POSTCODE = "KA3 6AY"
    BASE_URL = "https://morrisequestrian.co.uk"
    HEADERS = {"User-Agent": BROWSER_UA}
