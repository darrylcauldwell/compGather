"""Pony Club affiliation is derived from source structure, not the event name.

Many Pony Club events are named after their hunt/branch ("Barlow Hunt Mounted
Games Rally") and never contain the words "Pony Club" or "PC", so keyword
matching alone misses them and they leak past the Prepare "Hide Pony Club"
filter. The horse-events.co.uk parser knows these come from the
``/pony-club-rallies/`` section, so it stamps ``affiliation="pony-club"`` on
them; the scanner turns that into an ``affiliation:pony-club`` tag.
"""

from __future__ import annotations

from datetime import date

from bs4 import BeautifulSoup

from app.parsers.horse_events import HorseEventsParser
from app.services.tag_manager import extract_tags

_TODAY = date(2026, 1, 1)


def _listing_item(href: str, title: str) -> BeautifulSoup:
    html = (
        f'<div class="search-result" data-href="{href}">'
        f"<h3>{title}</h3>"
        "<span>15 August 2026 Location: Barlow</span>"
        "</div>"
    )
    return BeautifulSoup(html, "html.parser").find("div")


def test_pony_club_rally_gets_affiliation_from_url_not_name():
    # No "Pony Club"/"PC" anywhere in the title — only the URL section reveals it.
    item = _listing_item(
        "https://www.horse-events.co.uk/pony-club-rallies/barlow-hunt-mg-rally/",
        "Barlow Hunt Mounted Games Rally",
    )
    event = HorseEventsParser()._parse_listing_item(item, _TODAY)
    assert event is not None
    assert event.affiliation == "pony-club"


def test_general_event_has_no_affiliation():
    item = _listing_item(
        "https://www.horse-events.co.uk/horse-events/aston-le-walls-ode/",
        "Aston-le-Walls One Day Event",
    )
    event = HorseEventsParser()._parse_listing_item(item, _TODAY)
    assert event is not None
    assert event.affiliation is None


def test_source_affiliation_tags_branch_named_pc_event():
    # A hunt/branch-named event with no PC keyword still gets the tag when the
    # parser supplies the affiliation (threaded via source_affiliation).
    tags = extract_tags(
        name="Barlow Hunt Mounted Games Rally",
        event_type="training",
        source_affiliation="pony-club",
    )
    assert "affiliation:pony-club" in tags
