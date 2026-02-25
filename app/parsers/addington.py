from __future__ import annotations

from app.parsers.bases import BROWSER_UA, TribeEventsParser
from app.parsers.registry import register_parser


@register_parser("addington")
class AddingtonParser(TribeEventsParser):
    """Parser for addington.co.uk — Tribe Events Calendar REST API.

    All events are at Addington Equestrian Centre (MK18 2JR).
    """

    VENUE_NAME = "Addington"
    VENUE_POSTCODE = "MK18 2JR"
    BASE_URL = "https://addington.co.uk"
    HEADERS = {"User-Agent": BROWSER_UA}
