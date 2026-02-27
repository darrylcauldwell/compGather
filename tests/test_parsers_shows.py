"""Tests for major spectator show parsers.

Each parser returns static event data with a site-reachability check.
We mock the HTTP call and verify the returned event structure.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.parsers.aachen import AachenParser
from app.parsers.al_shiraaa import AlShiraaaParser
from app.parsers.arc_de_triomphe import ArcDeTriompheParser
from app.parsers.azelhof import AzelhofParser
from app.parsers.bolesworth import BolesworthParser
from app.parsers.brussels_stephex import BrusselsStephexParser
from app.parsers.carolina_international import CarolinaInternationalParser
from app.parsers.cavaliada import CAVALIADAParser
from app.parsers.chantilly import ChantillyParser
from app.parsers.chatsworth import ChatsworthParser
from app.parsers.chi_geneva import CHIGenevaParser
from app.parsers.chio_rotterdam import CHIORotterdamParser
from app.parsers.csio_barcelona import CSIOBarcelonaParser
from app.parsers.csio_roma import CSIORomaParser
from app.parsers.deauville import DeauvilleParser
from app.parsers.desert_international import DesertInternationalParser
from app.parsers.devon_horse_show import DevonHorseShowParser
from app.parsers.dinard import DinardParser
from app.parsers.dressage_at_devon import DressageAtDevonParser
from app.parsers.dubai_sj_championship import DubaiSJChampionshipParser
from app.parsers.dublin_horse_show import DublinHorseShowParser
from app.parsers.dutch_masters import DutchMastersParser
from app.parsers.equitalyon import EquitaLyonParser
from app.parsers.falsterbo import FalsterboParser
from app.parsers.fei_world_cup_finals import FEIWorldCupFinalsParser
from app.parsers.fontainebleau import FontainebleauParser
from app.parsers.global_dressage_festival import GlobalDressageFestivalParser
from app.parsers.gothenburg import GothenburgParser
from app.parsers.great_meadow import GreatMeadowParser
from app.parsers.great_yorkshire import GreatYorkshireParser
from app.parsers.hampton_classic import HamptonClassicParser
from app.parsers.helsinki_horse_show import HelsinkiHorseShowParser
from app.parsers.hof_kasselmann import HofKasselmannParser
from app.parsers.hope_show import HopeShowParser
from app.parsers.hoys import HOYSParser
from app.parsers.jumping_amsterdam import JumpingAmsterdamParser
from app.parsers.jumping_indoor_maastricht import JumpingIndoorMaastrichtParser
from app.parsers.jumping_verona import JumpingVeronaParser
from app.parsers.kentucky_three_day import KentuckyThreeDayParser
from app.parsers.keysoe_international import KeysoeInternationalParser
from app.parsers.la_baule import LaBauleParser
from app.parsers.lake_placid import LakePlacidParser
from app.parsers.le_siepi import LeSiepiParser
from app.parsers.lgct import LGCTParser
from app.parsers.live_oak import LiveOakParser
from app.parsers.london_international import LondonInternationalParser
from app.parsers.luhmuhlen import LuhmuhlenParser
from app.parsers.madrid_horse_week import MadridHorseWeekParser
from app.parsers.maryland_5_star import Maryland5StarParser
from app.parsers.mondial_du_lion import MondialDuLionParser
from app.parsers.munich_riem import MunichRiemParser
from app.parsers.national_equine_show import NationalEquineShowParser
from app.parsers.national_horse_show import NationalHorseShowParser
from app.parsers.ocala import OcalaParser
from app.parsers.old_salem_farm import OldSalemFarmParser
from app.parsers.oslo_horse_show import OsloHorseShowParser
from app.parsers.osberton import OsbertonParser
from app.parsers.pau import PauParser
from app.parsers.peelbergen import PeelbergenParser
from app.parsers.pennsylvania_national import PennsylvaniaNationalParser
from app.parsers.riesenbeck import RiesenbeckParser
from app.parsers.royal_cornwall import RoyalCornwallParser
from app.parsers.royal_highland import RoyalHighlandParser
from app.parsers.royal_welsh import RoyalWelshParser
from app.parsers.royal_windsor import RoyalWindsorParser
from app.parsers.samorin import SamorinParser
from app.parsers.saut_hermes import SautHermesParser
from app.parsers.scandinavia_jumping import ScandinaviaJumpingParser
from app.parsers.sentower_park import SentowerParkParser
from app.parsers.spruce_meadows import SpruceMeadowsParser
from app.parsers.stockholm_horse_show import StockholmHorseShowParser
from app.parsers.sunshine_tour import SunshineTourParser
from app.parsers.toscana_tour import ToscanaTourParser
from app.parsers.trailblazers import TrailblazersParser
from app.parsers.traverse_city import TraverseCityParser
from app.parsers.uae_presidents_cup import UAEPresidentsCupParser
from app.parsers.upperville import UppervilleParser
from app.parsers.washington_international import WashingtonInternationalParser
from app.parsers.wef import WEFParser
from app.parsers.vilamoura import VilamouraParser
from app.parsers.your_horse_live import YourHorseLiveParser

FIXTURES_DIR = Path(__file__).parent / "fixtures"

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
    (PauParser, "Les 5 Etoiles de Pau 2026", "2026-10-22", "2026-10-25", "Domaine de Sers, Pau", "Eventing"),
    (LuhmuhlenParser, "Luhmuhlen Horse Trials 2026", "2026-06-18", "2026-06-21", "Luhmuhlen", "Eventing"),
    (Maryland5StarParser, "Maryland 5 Star at Fair Hill 2026", "2026-10-15", "2026-10-18", "Fair Hill", "Eventing"),
    (OcalaParser, "Ocala Winter Spectacular 2026", "2025-12-31", "2026-03-22", "World Equestrian Center, Ocala", "Show Jumping"),
    (ArcDeTriompheParser, "Prix de l'Arc de Triomphe 2026", "2026-10-03", "2026-10-04", "ParisLongchamp", "Flat Racing"),
    (SpruceMeadowsParser, "Spruce Meadows Masters 2026", "2026-09-09", "2026-09-13", "Spruce Meadows", "Show Jumping"),
    (GothenburgParser, "Gothenburg Horse Show 2026", "2026-02-18", "2026-02-22", "Scandinavium, Gothenburg", "Show Jumping"),
    (ScandinaviaJumpingParser, "Scandinavia Jumping Tour 2026", "2026-02-06", "2026-02-14", "Odense Congress Center", "Show Jumping"),
    (JumpingIndoorMaastrichtParser, "Jumping Indoor Maastricht 2026", "2026-11-05", "2026-11-08", "MECC Maastricht", "Show Jumping"),
    (SautHermesParser, "Saut Hermès 2026", "2026-03-20", "2026-03-22", "Grand Palais, Paris", "Show Jumping"),
    (EquitaLyonParser, "Equita Lyon 2026", "2026-10-28", "2026-11-01", "Eurexpo Lyon", "Show Jumping"),
    (MunichRiemParser, "Pferd International München 2026", "2026-05-14", "2026-05-17", "Olympia-Reitanlage München-Riem", "Show Jumping"),
    (JumpingAmsterdamParser, "Jumping Amsterdam 2026", "2026-01-22", "2026-01-25", "RAI Amsterdam", "Show Jumping"),
    (DutchMastersParser, "The Dutch Masters 2026", "2026-03-12", "2026-03-15", "Brabanthallen, Den Bosch", "Show Jumping"),
    (CHIORotterdamParser, "CHIO Rotterdam 2026", "2026-06-18", "2026-06-21", "Kralingse Bos, Rotterdam", "Show Jumping"),
    (CHIGenevaParser, "CHI Geneva 2026", "2026-12-10", "2026-12-13", "Palexpo, Geneva", "Show Jumping"),
    (DublinHorseShowParser, "Dublin Horse Show 2026", "2026-08-05", "2026-08-09", "RDS, Dublin", "Show Jumping"),
    (CSIORomaParser, "CSIO Roma — Piazza di Siena 2026", "2026-05-28", "2026-05-31", "Piazza di Siena, Roma", "Show Jumping"),
    (JumpingVeronaParser, "Jumping Verona — Fieracavalli 2026", "2026-11-05", "2026-11-08", "Veronafiere", "Show Jumping"),
    (CSIOBarcelonaParser, "CSIO Barcelona 2026", "2026-10-01", "2026-10-04", "Real Club de Polo, Barcelona", "Show Jumping"),
    (HelsinkiHorseShowParser, "Helsinki International Horse Show 2026", "2026-10-22", "2026-10-25", "Messukeskus, Helsinki", "Show Jumping"),
    (MadridHorseWeekParser, "Madrid Horse Week 2026", "2026-11-26", "2026-11-29", "IFEMA, Madrid", "Show Jumping"),
    (OsloHorseShowParser, "Oslo Horse Show 2026", "2026-10-09", "2026-10-11", "Telenor Arena, Oslo", "Show Jumping"),
    (StockholmHorseShowParser, "Stockholm International Horse Show 2026", "2026-11-27", "2026-11-29", "Friends Arena, Stockholm", "Show Jumping"),
    (CAVALIADAParser, "CAVALIADA Krakow 2026", "2026-02-26", "2026-03-01", "Tauron Arena, Krakow", "Show Jumping"),
    (LaBauleParser, "Jumping La Baule CSIO5* 2026", "2026-06-11", "2026-06-14", "Stade Francois Andre, La Baule", "Show Jumping"),
    (MondialDuLionParser, "Mondial du Lion 2026", "2026-10-15", "2026-10-18", "Le Lion d'Angers", "Eventing"),
    (BrusselsStephexParser, "Brussels Stephex Masters 2026", "2026-08-27", "2026-08-30", "Stephex Stables, Brussels", "Show Jumping"),
    # USA — Tier 1
    (KentuckyThreeDayParser, "Kentucky Three-Day Event CCI5*-L 2026", "2026-04-23", "2026-04-26", "Kentucky Horse Park, Lexington", "Eventing"),
    (DevonHorseShowParser, "Devon Horse Show 2026", "2026-05-21", "2026-06-01", "Devon Horse Show Grounds", "Show Jumping"),
    (DressageAtDevonParser, "Dressage at Devon 2026", "2026-09-22", "2026-09-27", "Devon Horse Show Grounds", "Dressage"),
    (HamptonClassicParser, "Hampton Classic Horse Show 2026", "2026-08-23", "2026-08-30", "Hampton Classic Showgrounds, Bridgehampton", "Show Jumping"),
    (WashingtonInternationalParser, "Washington International Horse Show 2026", "2026-10-19", "2026-10-25", "Show Place Arena, Upper Marlboro", "Show Jumping"),
    (NationalHorseShowParser, "National Horse Show 2026", "2026-10-21", "2026-11-01", "Tryon International Equestrian Center", "Show Jumping"),
    (UppervilleParser, "Upperville Colt & Horse Show 2026", "2026-06-01", "2026-06-07", "Grafton & Salem Showgrounds, Upperville", "Show Jumping"),
    (PennsylvaniaNationalParser, "Pennsylvania National Horse Show 2026", "2026-10-08", "2026-10-18", "Pennsylvania Farm Show Complex, Harrisburg", "Show Jumping"),
    (GreatMeadowParser, "MARS Great Meadow International 2026", "2026-07-03", "2026-07-05", "Great Meadow, The Plains", "Eventing"),
]

# International single-event show parsers with no discipline (multi-discipline events)
INTERNATIONAL_MULTI_DISCIPLINE_PARSERS = [
    (FalsterboParser, "Falsterbo Horse Show 2026", "2026-07-04", "2026-07-12", "Falsterbo Horse Show"),
    (FontainebleauParser, "Grand Parquet Fontainebleau 2026", "2026-04-16", "2026-04-26", "Grand Parquet, Fontainebleau"),
    (FEIWorldCupFinalsParser, "FEI World Cup Finals 2026", "2026-04-08", "2026-04-12", "Dickies Arena, Fort Worth"),
    (LiveOakParser, "Live Oak International 2026", "2026-03-12", "2026-03-15", "Live Oak Stud, Ocala"),
]

# International single-event competition parsers: (class, name, start, end, venue, discipline)
INTERNATIONAL_COMPETITION_PARSERS = [
    (UAEPresidentsCupParser, "CSI5* UAE President's Cup 2026", "2026-01-07", "2026-01-11", "Abu Dhabi Equestrian Club", "Show Jumping"),
    (AlShiraaaParser, "Al Shira'aa International Horse Show 2026", "2026-01-20", "2026-01-25", "Al Forsan International Sports Resort", "Show Jumping"),
    (DubaiSJChampionshipParser, "Dubai Show Jumping Championship CSI5* 2026", "2026-01-15", "2026-01-18", "Emirates Equestrian Centre", "Show Jumping"),
    (KeysoeInternationalParser, "Keysoe International CSI2* 2026", "2026-07-02", "2026-07-04", "The College Equestrian Centre, Keysoe", "Show Jumping"),
    (ChantillyParser, "Chantilly Classic 2026", "2026-07-10", "2026-07-13", "Domaine de Chantilly", "Show Jumping"),
    (LeSiepiParser, "Adriatic Tour 2026", "2026-07-30", "2026-08-02", "Circolo Ippico Le Siepi", "Show Jumping"),
    (DinardParser, "Jumping International de Dinard CSI5* 2026", "2026-07-30", "2026-08-02", "Hippodrome de Dinard", "Show Jumping"),
    (DeauvilleParser, "Jumping International de Deauville CSI4* 2026", "2026-08-13", "2026-08-16", "Pole International du Cheval, Deauville", "Show Jumping"),
    (CarolinaInternationalParser, "Carolina International CCI4*-S 2026", "2026-03-19", "2026-03-22", "Carolina Horse Park, Raeford", "Eventing"),
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


@pytest.mark.parametrize(
    "parser_cls,expected_name,expected_start,expected_end,expected_venue",
    INTERNATIONAL_MULTI_DISCIPLINE_PARSERS,
    ids=[p[0].__name__ for p in INTERNATIONAL_MULTI_DISCIPLINE_PARSERS],
)
@pytest.mark.asyncio
async def test_international_multi_discipline_parser(
    parser_cls, expected_name, expected_start, expected_end, expected_venue
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
    assert event.venue_postcode is None
    assert event.discipline is None  # Multi-discipline — classifier decides
    assert event.event_type == "show"
    assert event.latitude is not None
    assert event.longitude is not None


@pytest.mark.parametrize(
    "parser_cls,expected_name,expected_start,expected_end,expected_venue,expected_discipline",
    INTERNATIONAL_COMPETITION_PARSERS,
    ids=[p[0].__name__ for p in INTERNATIONAL_COMPETITION_PARSERS],
)
@pytest.mark.asyncio
async def test_international_competition_parser(
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
    assert event.discipline == expected_discipline
    assert event.event_type == "competition"
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


@pytest.mark.asyncio
async def test_sunshine_tour_weekly_events():
    """Sunshine Tour parser should emit one competition per week from JSON API."""
    parser = SunshineTourParser()
    fixture = json.loads((FIXTURES_DIR / "sunshine_tour_api.json").read_text())

    mock_client = _mock_client()
    mock_client.get = AsyncMock(
        return_value=MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(return_value=fixture),
        )
    )

    with patch.object(parser, "_make_client", return_value=mock_client):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 3

    # All events should be competitions at Montenmedio
    for event in events:
        assert event.event_type == "competition"
        assert event.discipline == "Show Jumping"
        assert event.venue_name == "Montenmedio"
        assert event.latitude == 36.2519
        assert event.longitude == -5.8686

    # Check week codes appear in names
    assert "PW1" in events[0].name
    assert "W1" in events[1].name
    assert "W4" in events[2].name

    # Check dates are sequential
    assert events[0].date_start < events[1].date_start < events[2].date_start


@pytest.mark.asyncio
async def test_sunshine_tour_fallback_on_failure():
    """Sunshine Tour parser should fall back to static data when JSON fetch fails."""
    parser = SunshineTourParser()

    mock_client = _mock_client()
    mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))

    with patch.object(parser, "_make_client", return_value=mock_client):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 1
    assert events[0].name == "Andalucia Sunshine Tour 2026"
    assert events[0].event_type == "competition"
    assert events[0].discipline == "Show Jumping"


@pytest.mark.asyncio
async def test_azelhof_returns_all_fixtures():
    """Azelhof parser should emit one event per tour week across the season."""
    parser = AzelhofParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 9
    assert events[0].name == "Azelhof Autumn Tour Week 1"
    assert events[0].date_start == "2025-11-05"
    assert "CDI Lier" in events[5].name
    assert events[-1].name == "Azelhof Spring Tour Week 3"
    assert events[-1].date_end == "2026-03-29"
    for event in events:
        assert event.discipline == "Show Jumping"
        assert event.event_type == "competition"
        assert event.venue_name == "Azelhof"
        assert event.venue_postcode is None
        assert event.latitude is not None
        assert event.longitude is not None
        assert event.date_start < event.date_end


@pytest.mark.asyncio
async def test_sentower_park_returns_all_fixtures():
    """Sentower Park parser should emit one event per competition week."""
    parser = SentowerParkParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 4
    assert events[0].name == "Sentower Park CSI November"
    assert events[-1].name == "Zangersheide International"
    assert events[-1].date_start == "2026-02-25"
    for event in events:
        assert event.discipline == "Show Jumping"
        assert event.event_type == "competition"
        assert event.venue_name == "Sentower Park"
        assert event.venue_postcode is None
        assert event.latitude is not None
        assert event.longitude is not None
        assert event.date_start < event.date_end


@pytest.mark.asyncio
async def test_vilamoura_returns_all_fixtures():
    """Vilamoura parser should emit events for autumn Classic Tours."""
    parser = VilamouraParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 6
    assert "Tour II Week 1" in events[0].name
    assert "Tour III Week 3" in events[-1].name
    assert events[0].date_start == "2026-10-20"
    assert events[-1].date_end == "2026-12-06"
    for event in events:
        assert event.discipline == "Show Jumping"
        assert event.event_type == "competition"
        assert event.venue_name == "Vilamoura Equestrian Centre"
        assert event.venue_postcode is None
        assert event.latitude is not None
        assert event.longitude is not None
        assert event.date_start < event.date_end


@pytest.mark.asyncio
async def test_riesenbeck_returns_all_fixtures():
    """Riesenbeck parser should emit non-LGCT CSI events."""
    parser = RiesenbeckParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 2
    assert "February" in events[0].name
    assert "May" in events[1].name
    for event in events:
        assert event.discipline == "Show Jumping"
        assert event.event_type == "competition"
        assert event.venue_name == "Riesenbeck International"
        assert event.latitude is not None
        assert event.date_start < event.date_end


@pytest.mark.asyncio
async def test_hof_kasselmann_returns_all_fixtures():
    """Hof Kasselmann parser should emit Horses & Dreams and Nations Cup."""
    parser = HofKasselmannParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 2
    assert "Horses & Dreams" in events[0].name
    assert "Nations Cup" in events[1].name
    for event in events:
        assert event.discipline == "Show Jumping"
        assert event.event_type == "show"
        assert event.venue_name == "Hof Kasselmann"
        assert event.latitude is not None
        assert event.date_start < event.date_end


@pytest.mark.asyncio
async def test_peelbergen_returns_all_fixtures():
    """Peelbergen parser should emit key CSI events."""
    parser = PeelbergenParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 2
    assert "February" in events[0].name
    assert "EEF Series" in events[1].name
    for event in events:
        assert event.discipline == "Show Jumping"
        assert event.event_type == "competition"
        assert event.venue_name == "Peelbergen Equestrian Centre"
        assert event.latitude is not None
        assert event.date_start < event.date_end


@pytest.mark.asyncio
async def test_bolesworth_returns_all_fixtures():
    """Bolesworth parser should emit two weekly CSI4* events."""
    parser = BolesworthParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 2
    assert "Week 1" in events[0].name
    assert "Week 2" in events[1].name
    for event in events:
        assert event.discipline == "Show Jumping"
        assert event.event_type == "competition"
        assert event.venue_name == "Bolesworth Castle"
        assert event.venue_postcode == "SY14 8DD"
        assert event.date_start < event.date_end


@pytest.mark.asyncio
async def test_toscana_tour_returns_all_fixtures():
    """Toscana Tour parser should emit 4 weekly CSI events."""
    parser = ToscanaTourParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 4
    assert "Week 1" in events[0].name
    assert "Week 4" in events[3].name
    assert events[0].date_start == "2026-03-17"
    assert events[3].date_end == "2026-04-12"
    for event in events:
        assert event.discipline == "Show Jumping"
        assert event.event_type == "competition"
        assert event.venue_name == "Arezzo Equestrian Centre"
        assert event.latitude is not None
        assert event.date_start < event.date_end


@pytest.mark.asyncio
async def test_samorin_returns_all_fixtures():
    """Samorin parser should emit 3 CSI events across the season."""
    parser = SamorinParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 3
    assert "Spring" in events[0].name
    assert "Nations Cup" in events[1].name
    assert "Autumn" in events[2].name
    for event in events:
        assert event.discipline == "Show Jumping"
        assert event.event_type == "competition"
        assert event.venue_name == "X-Bionic Sphere, Samorin"
        assert event.latitude is not None
        assert event.date_start < event.date_end


# --- US multi-fixture tests ---


@pytest.mark.asyncio
async def test_wef_returns_all_weeks():
    """WEF parser should emit 13 weekly competition events."""
    parser = WEFParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 13
    assert "Week 1" in events[0].name
    assert "Grand Finale" in events[12].name
    assert events[0].date_start == "2025-12-31"
    assert events[12].date_end == "2026-03-29"
    for event in events:
        assert event.discipline == "Show Jumping"
        assert event.event_type == "competition"
        assert event.venue_name == "Wellington International"
        assert event.latitude is not None
        assert event.date_start < event.date_end


@pytest.mark.asyncio
async def test_gdf_returns_all_weeks():
    """Global Dressage Festival parser should emit 10 weekly events."""
    parser = GlobalDressageFestivalParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 10
    assert "Week 1" in events[0].name
    assert "Finale" in events[9].name
    assert events[0].date_start == "2026-01-07"
    for event in events:
        assert event.discipline == "Dressage"
        assert event.event_type == "competition"
        assert event.venue_name == "Equestrian Village, Wellington"
        assert event.latitude is not None
        assert event.date_start < event.date_end


@pytest.mark.asyncio
async def test_desert_international_returns_all_fixtures():
    """Desert International parser should emit 6 circuit weeks."""
    parser = DesertInternationalParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 6
    assert "Circuit 1" in events[0].name
    assert "CSI5*-W" in events[3].name
    for event in events:
        assert event.discipline == "Show Jumping"
        assert event.event_type == "competition"
        assert event.venue_name == "Desert International Horse Park, Thermal"
        assert event.latitude is not None
        assert event.date_start < event.date_end


@pytest.mark.asyncio
async def test_traverse_city_returns_all_fixtures():
    """Traverse City parser should emit key summer/fall CSI events."""
    parser = TraverseCityParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 8
    assert "Spring I" in events[0].name
    assert "Fall International" in events[7].name
    assert "CSI5*-W" in events[7].name
    for event in events:
        assert event.discipline == "Show Jumping"
        assert event.event_type == "competition"
        assert event.venue_name == "Flintfields Horse Park, Traverse City"
        assert event.latitude is not None
        assert event.date_start < event.date_end


@pytest.mark.asyncio
async def test_lake_placid_returns_all_fixtures():
    """Lake Placid parser should emit 2 consecutive weekly shows."""
    parser = LakePlacidParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 2
    assert "Lake Placid" in events[0].name
    assert "I Love New York" in events[1].name
    for event in events:
        assert event.discipline == "Show Jumping"
        assert event.event_type == "competition"
        assert event.venue_name == "Lake Placid Horse Show Grounds"
        assert event.date_start < event.date_end


@pytest.mark.asyncio
async def test_old_salem_farm_returns_all_fixtures():
    """Old Salem Farm parser should emit spring weeks + Gold Cup."""
    parser = OldSalemFarmParser()

    with patch.object(parser, "_make_client", return_value=_mock_client()):
        events = await parser.fetch_and_parse(parser.BASE_URL)

    assert len(events) == 3
    assert "Spring" in events[0].name
    assert "Gold Cup" in events[2].name
    for event in events:
        assert event.discipline == "Show Jumping"
        assert event.event_type == "competition"
        assert event.venue_name == "Old Salem Farm, North Salem"
        assert event.latitude is not None
        assert event.date_start < event.date_end
