from __future__ import annotations

from app.parsers.equus_organiser import EquusOrganiserParser
from app.parsers.registry import register_parser


@register_parser("nvec")
class NVECParser(EquusOrganiserParser):
    """Newbold Verdon Equestrian Centre — Equus Organiser platform.

    Fixed venue: Newbold Verdon EC, LE9 9NE.
    """

    SUBDOMAIN = "nvec"
    VENUE_NAME = "Newbold Verdon Equestrian Centre"
    VENUE_POSTCODE = "LE9 9NE"
