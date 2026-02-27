"""Tests for major spectator show parsers.

Each parser returns static event data with a site-reachability check.
We mock the HTTP call and verify the returned event structure.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.parsers.aachen import AachenParser
from app.parsers.arc_de_triomphe import ArcDeTriompheParser
from app.parsers.chatsworth import ChatsworthParser
from app.parsers.great_yorkshire import GreatYorkshireParser
from app.parsers.hope_show import HopeShowParser
from app.parsers.hoys import HOYSParser
from app.parsers.lgct import LGCTParser
from app.parsers.london_international import LondonInternationalParser
from app.parsers.luhmuhlen import LuhmuhlenParser
from app.parsers.national_equine_show import NationalEquineShowParser
from app.parsers.maryland_5_star import Maryland5StarParser
from app.parsers.ocala import OcalaParser
from app.parsers.osberton import OsbertonParser
from app.parsers.pau import PauParser
from app.parsers.royal_cornwall import RoyalCornwallParser
from app.parsers.royal_highland import RoyalHighlandParser
from app.parsers.royal_welsh import RoyalWelshParser
from app.parsers.royal_windsor import RoyalWindsorParser
from app.parsers.spruce_meadows import SpruceMeadowsParser
from app.parsers.sunshine_tour import SunshineTourParser
from app.parsers.trailblazers import TrailblazersParser
from app.parsers.your_horse_live import YourHorseLiveParser

# Single-venue UK show parsers: (class, name, start, end, venue, postcode)
UK_SHOW_PARSERS = [
    (HOYSParser, "Horse of the Year Show 2026", "2026-10-07", "2026-10-11", "NEC Birmingham", "B40 1NT"),
    (LondonInternationalParser, "London International Horse Show 2026", "2026-12-17", "2026-12-21", "ExCeL London", "E16 1XL"),
    (RoyalWindsorParser, "Royal Windsor Horse Show 2026", "2026-05-14", "2026-05-17", "Royal Windsor Horse Show", "SL4 1NG"),
    (YourHorseLiveParser, "Your Horse Live 2026", "2026-11-06", "2026-11-08", "Stoneleigh Park", "CV8 2LZ"),
    (GreatYorkshireParser, "Great Yorkshire Show 2026", "2026-07-14", "2026-07-17", "Great Yorkshire Showground", "HG2 8NZ"),
    (RoyalHighlandParser, "Royal Highland Show 2026", "2026-06-18", "2026-06-21", "Royal Highland Showground", "EH28 8NB"),
    (RoyalWelshParser, "Royal Welsh Show 2026", "2026-07-20", "2026-07-23", "Royal Welsh Showground", "LD2 3SY"),
    (RoyalCornwallParser, "Royal Cornwall Show 2026", "2026-06-04", "2026-06-06", "Royal Cornwall Showground", "PL27 7JE"),
    (HopeShowParser, "Hope Show 2026", "2026-08-31", None, "Hope Showground", "S33 8RZ"),
    (ChatsworthParser, "Chatsworth Country Fair 2026", "2026-09-04", "2026-09-06", "Chatsworth House", "DE45 1PP"),
    (NationalEquineShowParser, "National Equine Show 2026", "2026-02-28", "2026-03-01", "NEC Birmingham", "B40 1NT"),
]

# International show parsers: (class, name, start, end, venue, discipline)
INTERNATIONAL_PARSERS = [
    (SunshineTourParser, "Andalucia Sunshine Tour 2026", "2026-02-02", "2026-03-22", "Montenmedio", "Show Jumping"),
    (PauParser, "Les 5 Etoiles de Pau 2026", "2026-10-22", "2026-10-25", "Domaine de Sers, Pau", "Eventing"),
    (LuhmuhlenParser, "Luhmuhlen Horse Trials 2026", "2026-06-18", "2026-06-21", "Luhmuhlen", "Eventing"),
    (Maryland5StarParser, "Maryland 5 Star at Fair Hill 2026", "2026-10-15", "2026-10-18", "Fair Hill", "Eventing"),
    (OcalaParser, "Ocala Winter Spectacular 2026", "2025-12-31", "2026-03-22", "World Equestrian Center, Ocala", "Show Jumping"),
    (ArcDeTriompheParser, "Prix de l'Arc de Triomphe 2026", "2026-10-03", "2026-10-04", "ParisLongchamp", "Flat Racing"),
    (SpruceMeadowsParser, "Spruce Meadows Masters 2026", "2026-09-09", "2026-09-13", "Spruce Meadows", "Show Jumping"),
]


def _mock_client():
    """Create a mock httpx.AsyncClient that returns 200."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


@pytest.mark.parametrize(
    "parser_cls,expected_name,expected_start,expected_end,expected_venue,expected_postcode",
    UK_SHOW_PARSERS,
    ids=[p[0].__name__ for p in UK_SHOW_PARSERS],
)
@pytest.mark.asyncio
async def test_uk_show_parser(
    parser_cls, expected_name, expected_start, expected_end, expected_venue, expected_postcode
):
    parser = parser_cls()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 1
    event = events[0]
    assert event.name == expected_name
    assert event.date_start == expected_start
    assert event.date_end == expected_end
    if expected_end is not None:
        assert event.date_start < event.date_end
    assert event.venue_name == expected_venue
    assert event.venue_postcode == expected_postcode
    assert event.discipline is None  # Multi-discipline shows — classifier decides
    assert event.event_type == "show"


@pytest.mark.parametrize(
    "parser_cls,expected_name,expected_start,expected_end,expected_venue,expected_discipline",
    INTERNATIONAL_PARSERS,
    ids=[p[0].__name__ for p in INTERNATIONAL_PARSERS],
)
@pytest.mark.asyncio
async def test_international_parser(
    parser_cls, expected_name, expected_start, expected_end, expected_venue, expected_discipline
):
    parser = parser_cls()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 1
    event = events[0]
    assert event.name == expected_name
    assert event.date_start == expected_start
    assert event.date_end == expected_end
    assert event.date_start < event.date_end
    assert event.venue_name == expected_venue
    assert event.venue_postcode is None  # International — no UK postcode
    assert event.discipline == expected_discipline
    assert event.event_type == "show"
    assert event.latitude is not None
    assert event.longitude is not None


@pytest.mark.asyncio
async def test_lgct_parser_returns_all_stops():
    parser = LGCTParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 17

    # Check London stop specifically
    london = [e for e in events if "London" in e.name]
    assert len(london) == 1
    assert london[0].venue_name == "Royal Hospital Chelsea"
    assert london[0].venue_postcode == "SW3 4SR"
    assert london[0].date_start == "2026-08-07"
    assert london[0].date_end == "2026-08-09"

    # All events should be Show Jumping shows
    for event in events:
        assert event.discipline == "Show Jumping"
        assert event.event_type == "show"
        assert event.date_start < event.date_end
        assert event.venue_name


@pytest.mark.asyncio
async def test_osberton_returns_two_fixtures():
    parser = OsbertonParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 2
    assert events[0].name == "Osberton International Horse Trials (1) 2026"
    assert events[0].date_start == "2026-05-22"
    assert events[1].name == "Osberton International Horse Trials (2) 2026"
    assert events[1].date_start == "2026-10-02"
    for event in events:
        assert event.discipline == "Eventing"
        assert event.event_type == "show"
        assert event.venue_name == "Osberton"
        assert event.venue_postcode == "S80 2LW"


@pytest.mark.asyncio
async def test_trailblazers_parser():
    parser = TrailblazersParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 1
    event = events[0]
    assert event.name == "SEIB Trailblazers Championships 2026"
    assert event.date_start == "2026-07-31"
    assert event.date_end == "2026-08-03"
    assert event.venue_name == "Addington Manor"
    assert event.venue_postcode == "MK18 2JR"
    assert event.discipline is None
    assert event.event_type == "show"


@pytest.mark.asyncio
async def test_aachen_returns_two_fixtures():
    parser = AachenParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 2
    assert events[0].name == "TSCHIO Aachen 2026"
    assert events[0].date_start == "2026-05-22"
    assert events[0].date_end == "2026-05-24"
    assert events[1].name == "FEI World Championships Aachen 2026"
    assert events[1].date_start == "2026-08-11"
    assert events[1].date_end == "2026-08-23"
    for event in events:
        assert event.discipline is None
        assert event.event_type == "show"
        assert event.venue_name == "Aachen Soers"
        assert event.venue_postcode is None
        assert event.latitude is not None
        assert event.longitude is not None


@pytest.mark.asyncio
async def test_parser_handles_unreachable_site():
    """Parsers should return static data even when the site is unreachable."""
    parser = HOYSParser()

    mock_client = _mock_client()
    mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))

    with patch.object(parser, "_make_client", return_value=mock_client):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 1
    assert events[0].name == "Horse of the Year Show 2026"
