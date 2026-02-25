from __future__ import annotations

from app.parsers.bases import TribeEventsParser
from app.parsers.registry import register_parser


@register_parser("abbey_farm")
class AbbeyFarmParser(TribeEventsParser):
    """Parser for abbeyfarmequestrian.co.uk — WordPress + The Events Calendar REST API.

    Fixed venue: Abbey Farm Equestrian, DE4 2GL.
    """

    VENUE_NAME = "Abbey Farm Equestrian"
    VENUE_POSTCODE = "DE4 2GL"
    BASE_URL = "https://abbeyfarmequestrian.co.uk"
    USE_START_DATE = False
