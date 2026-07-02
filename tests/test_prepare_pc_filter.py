"""Pony Club affiliation tagging — powers the Prepare "Hide Pony Club" filter.

The affiliation:pony-club tag must catch the common PC forms (PC abbreviation,
PPC, Prince Philip, spelled-out) so the app can reliably exclude members-only
Pony Club events from Prepare. Previously only "pony club" spelled out matched,
so ~half the PC events (abbreviated / hunt-branch) went untagged.
"""

from __future__ import annotations

import pytest

from app.services.tag_manager import extract_tags


@pytest.mark.parametrize(
    "name",
    [
        "Cottesmore PC Rally with Willa",
        "Barlow Hunt PC Dressage with Sonia Baines",
        "Area 5 PPC Mounted Games",
        "Suffolk Pony Club Fun & Games Rally",
        "Prince Philip Cup Zone Qualifier",
    ],
)
def test_pony_club_events_are_tagged(name):
    assert "affiliation:pony-club" in extract_tags(name, event_type="training"), name


@pytest.mark.parametrize(
    "name",
    [
        "Spring Dressage Championship",
        "Aston-le-Walls One Day Event",
        "Helen Griffiths Dressage Clinic",
    ],
)
def test_non_pony_club_events_not_tagged(name):
    assert "affiliation:pony-club" not in extract_tags(name, event_type="training"), name
