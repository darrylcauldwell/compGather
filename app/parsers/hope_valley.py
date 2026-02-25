from __future__ import annotations

from app.parsers.bases import TribeEventsParser
from app.parsers.registry import register_parser


@register_parser("hope_valley")
class HopeValleyParser(TribeEventsParser):
    """Parser for hopevalleyridingclub.co.uk — WordPress + The Events Calendar REST API.

    Fixed venue: Hope Valley Riding Club, S33 6RB.
    """

    VENUE_NAME = "Hope Valley Riding Club"
    VENUE_POSTCODE = "S33 6RB"
    BASE_URL = "https://hopevalleyridingclub.co.uk"
