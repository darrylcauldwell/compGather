"""Fixture-based tests for the top 5 parsers.

Each test loads a synthetic HTML/JSON fixture and mocks httpx to return it,
then asserts the parser extracts the expected competitions.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import ExtractedCompetition

FIXTURES = Path(__file__).parent / "fixtures"


def _mock_response(fixture_or_content: str | Path, status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Response from a fixture file or inline content string."""
    path = Path(fixture_or_content)
    if path.exists():
        content = path.read_text()
    else:
        content = str(fixture_or_content)
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = content
    resp.raise_for_status = MagicMock()
    # For JSON APIs
    try:
        resp.json.return_value = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        resp.json.side_effect = ValueError("Not JSON")
    return resp


# ---------------------------------------------------------------------------
# Event classification tests
# ---------------------------------------------------------------------------
class TestClassifyEvent:
    """Tests for the classify_event() function — single source of truth for
    determining (discipline, event_type) from event name/description."""

    def test_clinic_is_training(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("Maddy Moffet Polework Training Clinic")
        assert event_type == "training"

    def test_workshop_is_training(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("Dressage Workshop with Jane Smith")
        assert discipline == "Dressage"
        assert event_type == "training"

    def test_rally_is_training(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("Saturday Rally")
        assert event_type == "training"

    def test_gridwork_is_training(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("February Grid Work")
        assert event_type == "training"

    def test_flatwork_is_training(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("Flatwork Training Session")
        assert event_type == "training"

    def test_polework_is_training(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("Polework with Shona Wallace")
        assert event_type == "training"

    def test_schooling_is_training(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("XC Schooling Day")
        assert event_type == "training"

    def test_arena_hire_is_venue_hire(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("Indoor Arena Hire")
        assert event_type == "venue_hire"

    def test_course_hire_is_venue_hire(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("Show Jumping Course Hire")
        assert discipline == "Show Jumping"
        assert event_type == "venue_hire"

    def test_show_jumping_competition(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("Spring Show Jumping Championship")
        assert discipline == "Show Jumping"
        assert event_type == "competition"

    def test_dressage_competition(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("Spring Dressage Show")
        assert discipline == "Dressage"
        assert event_type == "competition"

    def test_eventing_competition(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("Belton Park One Day Event")
        assert discipline == "Eventing"
        assert event_type == "competition"

    def test_cross_country_competition(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("Cross Country Fun Ride")
        assert discipline == "Cross Country"
        assert event_type == "competition"

    def test_hunter_trial_competition(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("Spring Hunter Trial")
        assert discipline == "Hunter Trial"
        assert event_type == "competition"

    def test_unknown_discipline_is_competition(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("Summer Fun Day")
        assert discipline is None
        assert event_type == "competition"

    def test_description_helps_classification(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event(
            "Spring Event", "Show jumping classes from 60cm to 1.10m"
        )
        assert discipline == "Show Jumping"
        assert event_type == "competition"

    def test_lesson_is_training(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("Private Lesson with David O'Brien")
        assert event_type == "training"

    def test_course_walk_is_training(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("XC Course Walk")
        assert event_type == "training"

    def test_camp_is_training(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("Somerford Pre season camp")
        assert event_type == "training"

    def test_stabling_is_venue_hire(self):
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("Stabling & Hook Ups")
        assert event_type == "venue_hire"

    def test_dressage_training_independent(self):
        """Discipline and event_type are determined independently."""
        from app.parsers.utils import classify_event
        discipline, event_type = classify_event("Dressage Training Session")
        assert discipline == "Dressage"
        assert event_type == "training"


class TestClassifyEventBackwardCompat:
    """Tests for backward-compatible wrappers that delegate to classify_event."""

    def test_infer_discipline_returns_discipline(self):
        from app.parsers.utils import infer_discipline
        # Polework Clinic → discipline=None (no competition discipline), event_type=training
        assert infer_discipline("Polework Clinic") is None

    def test_infer_discipline_returns_competition(self):
        from app.parsers.utils import infer_discipline
        assert infer_discipline("Show Jumping Championship") == "Show Jumping"

    def test_infer_discipline_returns_none(self):
        from app.parsers.utils import infer_discipline
        assert infer_discipline("Summer Fun Day") is None

    def test_should_skip_event_still_works(self):
        from app.parsers.utils import should_skip_event
        assert should_skip_event(None, "Polework with Shona Wallace") is True
        assert should_skip_event(None, "Spring Dressage Show") is False

    def test_is_competition_event_still_works(self):
        from app.parsers.utils import is_competition_event
        assert is_competition_event("Spring Dressage Show") is True
        assert is_competition_event("Indoor Arena Hire") is False

    def test_normalise_discipline_returns_canonical(self):
        from app.parsers.utils import normalise_discipline
        assert normalise_discipline("showjumping") == "Show Jumping"
        assert normalise_discipline("dressage") == "Dressage"

    def test_normalise_discipline_handles_composite(self):
        from app.parsers.utils import normalise_discipline
        assert normalise_discipline("Showing, Other") == "Showing"
        assert normalise_discipline("Showjumping, Hunter Trial/Cross Country") == "Show Jumping"

    def test_normalise_discipline_returns_none_for_empty(self):
        from app.parsers.utils import normalise_discipline
        assert normalise_discipline(None) is None
        assert normalise_discipline("") is None

    def test_normalise_arena_eventing(self):
        from app.parsers.utils import normalise_discipline
        assert normalise_discipline("arena eventing") == "Arena Eventing"

    def test_normalise_underscore_api_codes(self):
        """Underscore-separated API codes (e.g. Equipe) normalise correctly."""
        from app.parsers.utils import normalise_discipline
        assert normalise_discipline("show_jumping") == "Show Jumping"
        assert normalise_discipline("eventing") == "Eventing"
        assert normalise_discipline("driving") == "Driving"


# ---------------------------------------------------------------------------
# British Eventing
# ---------------------------------------------------------------------------
class TestBritishEventingParser:
    @pytest.mark.asyncio
    async def test_extracts_open_events(self):
        from app.parsers.british_eventing import BritishEventingParser

        fixture = FIXTURES / "british_eventing_events.html"
        mock_resp = _mock_response(fixture)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.bases.httpx.AsyncClient", return_value=mock_client):
            parser = BritishEventingParser()
            result = await parser.fetch_and_parse("https://example.com")

        # Should get 2 events (Belton Park + Tweseldown), cancelled event excluded
        assert len(result) == 2

        belton = result[0]
        assert belton.name == "Belton Park"
        assert belton.date_start == "2026-03-15"
        assert belton.date_end is None  # single-day
        assert belton.discipline == "Eventing"
        assert belton.classes == ["BE100", "BE90", "BE80"]

        tweseldown = result[1]
        assert tweseldown.name == "Tweseldown"
        assert tweseldown.date_start == "2026-03-28"
        assert tweseldown.date_end == "2026-03-29"

    @pytest.mark.asyncio
    async def test_skips_cancelled_events(self):
        from app.parsers.british_eventing import BritishEventingParser

        fixture = FIXTURES / "british_eventing_events.html"
        mock_resp = _mock_response(fixture)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.bases.httpx.AsyncClient", return_value=mock_client):
            parser = BritishEventingParser()
            result = await parser.fetch_and_parse("https://example.com")

        names = [r.name for r in result]
        assert "Cancelled Event" not in names


# ---------------------------------------------------------------------------
# British Eventing date parsing (unit tests, no HTTP mocking needed)
# ---------------------------------------------------------------------------
class TestBritishEventingDateParsing:
    def setup_method(self):
        from app.parsers.british_eventing import BritishEventingParser
        self.parser = BritishEventingParser()

    def test_single_date(self):
        start, end = self.parser._parse_be_date("15 Mar 26")
        assert start == "2026-03-15"
        assert end is None

    def test_same_month_range(self):
        start, end = self.parser._parse_be_date("28 - 29 Mar 26")
        assert start == "2026-03-28"
        assert end == "2026-03-29"

    def test_cross_month_range(self):
        start, end = self.parser._parse_be_date("28 Feb - 1 Mar 26")
        assert start == "2026-02-28"
        assert end == "2026-03-01"

    def test_invalid_date(self):
        start, end = self.parser._parse_be_date("not a date")
        assert start is None
        assert end is None


# ---------------------------------------------------------------------------
# Equipe Online
# ---------------------------------------------------------------------------
class TestEquipeOnlineParser:
    @pytest.mark.asyncio
    async def test_extracts_gbr_events_only(self):
        from app.parsers.equipe_online import EquipeOnlineParser

        fixture = FIXTURES / "equipe_online_meetings.json"
        meetings_resp = _mock_response(fixture)
        # Schedule endpoint returns empty for simplicity
        schedule_resp = MagicMock()
        schedule_resp.status_code = 200
        schedule_resp.json.return_value = []
        schedule_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=lambda url, **kw: (
            meetings_resp if "meetings" in url and "schedule" not in url
            else schedule_resp
        ))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.bases.httpx.AsyncClient", return_value=mock_client):
            parser = EquipeOnlineParser()
            result = await parser.fetch_and_parse("https://online.equipe.com")

        # Should exclude the FRA event; all GBR events captured (including placeholder venues)
        assert all(isinstance(r, ExtractedCompetition) for r in result)
        assert len(result) == 6  # 7 total minus 1 FRA event
        names = [r.name for r in result]
        assert "Some Event in France" not in names

    @pytest.mark.asyncio
    async def test_extracts_discipline(self):
        from app.parsers.equipe_online import EquipeOnlineParser

        fixture = FIXTURES / "equipe_online_meetings.json"
        meetings_resp = _mock_response(fixture)
        schedule_resp = MagicMock()
        schedule_resp.status_code = 200
        schedule_resp.json.return_value = []
        schedule_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=lambda url, **kw: (
            meetings_resp if "meetings" in url and "schedule" not in url
            else schedule_resp
        ))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.bases.httpx.AsyncClient", return_value=mock_client):
            parser = EquipeOnlineParser()
            result = await parser.fetch_and_parse("https://online.equipe.com")

        # Equipe API provides a top-level "discipline" field on some events;
        # the parser passes raw API codes as hints — classifier normalises later.
        # Events where "discipline" is nested inside "metadata" get discipline=None.
        disciplines = {r.name: r.discipline for r in result}
        # Top-level discipline field → raw API value passed as hint
        assert disciplines["Onley Grounds - Senior British Showjumping"] == "show_jumping"
        assert disciplines["Bicton : Unaffiliated Arena Eventing"] == "eventing"
        assert disciplines["Unknown Pattern Event"] == "show_jumping"
        # Events 50001/50002 have discipline in metadata only → parser returns None
        assert disciplines["Dressage Championships - Hartpury"] is None
        assert disciplines["British Showjumping - Eland Lodge"] is None


# ---------------------------------------------------------------------------
# Equipe Online venue extraction (unit tests, no HTTP mocking needed)
# ---------------------------------------------------------------------------
class TestEquipeVenueExtraction:
    """Tests for the multi-strategy venue extraction cascade."""

    def setup_method(self):
        from app.parsers.equipe_online import EquipeOnlineParser
        self.parser = EquipeOnlineParser()

    # --- Strategy 1: Separator-based ---

    def test_separator_dash(self):
        result = self.parser._extract_venue_name("Onley Grounds - Senior British Showjumping")
        assert result == "Onley Grounds"

    def test_separator_colon(self):
        result = self.parser._extract_venue_name("Bicton : Unaffiliated Arena Eventing")
        assert result == "Bicton"

    def test_separator_pipe(self):
        result = self.parser._extract_venue_name("Venue Name | Event Type")
        assert result == "Venue Name"

    def test_separator_takes_first_occurrence(self):
        result = self.parser._extract_venue_name("Addington Manor - SJ - Day 2")
        assert result == "Addington Manor"

    def test_separator_short_prefix_falls_through(self):
        """If the part before separator is <= 3 chars, skip to next strategy."""
        result = self.parser._extract_venue_name("BS - National Championships")
        # "BS" is only 2 chars, so separator strategy should be skipped
        # Keyword strategy should not match either (no venue before keyword)
        # Falls through to placeholder
        assert result == "Tbc"

    # --- Strategy 2: Keyword-based ---

    def test_keyword_british_showjumping(self):
        result = self.parser._extract_venue_name("Addington Manor Senior British Showjumping")
        assert result == "Addington Manor"

    def test_keyword_dressage(self):
        result = self.parser._extract_venue_name("Hartpury Dressage Championship")
        assert result == "Hartpury"

    def test_keyword_unaffiliated(self):
        result = self.parser._extract_venue_name("Kelsall Hill Unaffiliated Show Jumping")
        assert result == "Kelsall Hill"

    def test_keyword_at_start_returns_placeholder(self):
        """Keyword at the very start means no venue before it."""
        result = self.parser._extract_venue_name("Unaffiliated Showjumping")
        assert result == "Tbc"

    # --- Strategy 3: Placeholder fallback ---

    def test_unknown_pattern_returns_tbc(self):
        result = self.parser._extract_venue_name("Unknown Pattern Event")
        assert result == "Tbc"

    def test_empty_string_returns_tbc(self):
        result = self.parser._extract_venue_name("")
        assert result == "Tbc"

    # --- Return type guarantees ---

    def test_never_returns_none(self):
        """The method should always return a str, never None."""
        test_cases = [
            "Onley Grounds - Senior British Showjumping",
            "Bicton : Unaffiliated Arena Eventing",
            "Addington Manor Senior British Showjumping",
            "Unaffiliated Showjumping",
            "Unknown Pattern Event",
            "",
        ]
        for name in test_cases:
            result = self.parser._extract_venue_name(name)
            assert isinstance(result, str), f"Expected str for '{name}', got {type(result)}"
            assert len(result) > 0, f"Expected non-empty string for '{name}'"

    def test_valid_venues_longer_than_3_chars(self):
        """All valid venue names (non-Tbc) should be > 3 characters."""
        test_cases = [
            ("Onley Grounds - Senior British Showjumping", "Onley Grounds"),
            ("Bicton : Unaffiliated Arena Eventing", "Bicton"),
            ("Addington Manor Senior British Showjumping", "Addington Manor"),
        ]
        for name, expected in test_cases:
            result = self.parser._extract_venue_name(name)
            assert result == expected
            assert len(result) > 3

    # --- Parenthetical stripping ---

    def test_strips_trailing_parenthetical(self):
        result = self.parser._extract_venue_name("Hartpury Dressage (P-AM)")
        assert result == "Hartpury"


# ---------------------------------------------------------------------------
# Equipe Online integration test — all GBR events captured
# ---------------------------------------------------------------------------
class TestEquipeOnlineAllEventsCaptured:
    """Verify that events with placeholder venues are now included (not dropped)."""

    @pytest.mark.asyncio
    async def test_all_gbr_events_captured(self):
        from app.parsers.equipe_online import EquipeOnlineParser

        fixture = FIXTURES / "equipe_online_meetings.json"
        meetings_resp = _mock_response(fixture)
        schedule_resp = MagicMock()
        schedule_resp.status_code = 200
        schedule_resp.json.return_value = []
        schedule_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=lambda url, **kw: (
            meetings_resp if "meetings" in url and "schedule" not in url
            else schedule_resp
        ))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.bases.httpx.AsyncClient", return_value=mock_client):
            parser = EquipeOnlineParser()
            result = await parser.fetch_and_parse("https://online.equipe.com")

        # 6 GBR events in fixture (50001-50007 minus 50003 which is FRA)
        names = [r.name for r in result]
        assert len(result) == 6
        assert "Some Event in France" not in names

        # Verify separator-based extraction
        onley = next(r for r in result if "Onley" in r.name)
        assert onley.venue_name == "Onley Grounds"

        bicton = next(r for r in result if "Bicton" in r.name)
        assert bicton.venue_name == "Bicton"

        # Verify keyword-based extraction
        addington = next(r for r in result if "Addington" in r.name)
        assert addington.venue_name == "Addington Manor"

        # Verify placeholder fallback (event preserved, not dropped)
        unknown = next(r for r in result if "Unknown Pattern" in r.name)
        assert unknown.venue_name == "Tbc"

    @pytest.mark.asyncio
    async def test_venue_name_always_string(self):
        """Every extracted event should have a string venue_name, never None."""
        from app.parsers.equipe_online import EquipeOnlineParser

        fixture = FIXTURES / "equipe_online_meetings.json"
        meetings_resp = _mock_response(fixture)
        schedule_resp = MagicMock()
        schedule_resp.status_code = 200
        schedule_resp.json.return_value = []
        schedule_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=lambda url, **kw: (
            meetings_resp if "meetings" in url and "schedule" not in url
            else schedule_resp
        ))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.bases.httpx.AsyncClient", return_value=mock_client):
            parser = EquipeOnlineParser()
            result = await parser.fetch_and_parse("https://online.equipe.com")

        for comp in result:
            assert isinstance(comp.venue_name, str), f"venue_name is not str for {comp.name}"
            assert len(comp.venue_name) > 0, f"venue_name is empty for {comp.name}"


# ---------------------------------------------------------------------------
# Horse Monkey
# ---------------------------------------------------------------------------
class TestHorseMonkeyParser:
    @pytest.mark.asyncio
    async def test_extracts_competitions(self):
        from app.parsers.horse_monkey import HorseMonkeyParser

        fixture = FIXTURES / "horse_monkey_search.json"
        search_data = json.loads(Path(fixture).read_text())
        search_resp = MagicMock()
        search_resp.status_code = 200
        search_resp.json.return_value = search_data
        search_resp.raise_for_status = MagicMock()

        # Detail page for venue enrichment (empty — no coords)
        detail_resp = MagicMock()
        detail_resp.status_code = 200
        detail_resp.text = "<html><body>No coords here</body></html>"
        detail_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=search_resp)
        mock_client.get = AsyncMock(return_value=detail_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.bases.httpx.AsyncClient", return_value=mock_client):
            parser = HorseMonkeyParser()
            result = await parser.fetch_and_parse("https://horsemonkey.com")

        assert len(result) == 2

        spring = next(r for r in result if "Spring" in r.name)
        assert spring.venue_name == "Meadow Farm"
        assert spring.date_start == "2026-03-15"

        summer = next(r for r in result if "Summer" in r.name)
        assert summer.venue_name == "Bury Farm"
        assert summer.date_end == "2026-06-21"

    @pytest.mark.asyncio
    async def test_enriches_with_coordinates(self):
        from app.parsers.horse_monkey import HorseMonkeyParser

        fixture = FIXTURES / "horse_monkey_search.json"
        search_data = json.loads(Path(fixture).read_text())
        search_resp = MagicMock()
        search_resp.status_code = 200
        search_resp.json.return_value = search_data
        search_resp.raise_for_status = MagicMock()

        # Detail page WITH coordinates
        detail_resp = MagicMock()
        detail_resp.status_code = 200
        detail_resp.text = '<html><script>var m_show = {"latitude":"52.123","longitude":"-1.456"};</script></html>'
        detail_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=search_resp)
        mock_client.get = AsyncMock(return_value=detail_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.bases.httpx.AsyncClient", return_value=mock_client):
            parser = HorseMonkeyParser()
            result = await parser.fetch_and_parse("https://horsemonkey.com")

        # At least one should have coordinates from detail page enrichment
        coords = [(r.latitude, r.longitude) for r in result if r.latitude is not None]
        assert len(coords) > 0
        assert coords[0] == (52.123, -1.456)


# ---------------------------------------------------------------------------
# Pony Club
# ---------------------------------------------------------------------------
class TestPonyClubParser:
    @pytest.mark.asyncio
    async def test_extracts_events_from_calendar(self):
        from app.parsers.pony_club import PonyClubParser

        fixture = FIXTURES / "pony_club_calendar.html"
        calendar_resp = _mock_response(fixture)

        # Branch discovery returns no branches (to keep test simple)
        empty_resp = _mock_response("<html><body></body></html>")

        mock_client = AsyncMock()
        call_count = 0

        async def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return calendar_resp  # main calendar
            return empty_resp  # branch discovery

        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.bases.httpx.AsyncClient", return_value=mock_client):
            parser = PonyClubParser()
            result = await parser.fetch_and_parse("https://pcuk.org/calendar/")

        # All 3 events captured: 2 competitions + 1 rally (training)
        assert len(result) == 3

        sj = result[0]
        assert sj.name == "East Midlands Area: Area Show Jumping"
        assert sj.date_start == "2026-03-15"
        assert sj.venue_name == "Keysoe"
        # Parser passes raw data-event-type as discipline hint — classifier normalises later
        assert sj.discipline == "Show Jumping"

        dressage = result[1]
        assert dressage.venue_name == "Bicton Arena"
        assert dressage.discipline == "Dressage"

    @pytest.mark.asyncio
    async def test_rally_captured(self):
        """Pony Club rallies (training events) are now captured."""
        from app.parsers.pony_club import PonyClubParser

        fixture = FIXTURES / "pony_club_calendar.html"
        calendar_resp = _mock_response(fixture)
        empty_resp = _mock_response("<html><body></body></html>")

        mock_client = AsyncMock()
        call_count = 0

        async def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return calendar_resp
            return empty_resp

        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.bases.httpx.AsyncClient", return_value=mock_client):
            parser = PonyClubParser()
            result = await parser.fetch_and_parse("https://pcuk.org/calendar/")

        rally = next(r for r in result if "Rally" in r.name)
        assert rally.name == "North Herefordshire: Spring Rally"
        # Parser passes raw data-event-type as discipline hint — not a canonical discipline
        assert rally.discipline == "rally"


# ---------------------------------------------------------------------------
# British Showjumping (most complex — calendar + detail pages)
# ---------------------------------------------------------------------------
class TestBritishShowjumpingParser:
    @pytest.mark.asyncio
    async def test_extracts_from_calendar_page(self):
        from app.parsers.british_showjumping import BritishShowjumpingParser

        calendar_fixture = FIXTURES / "british_showjumping_calendar.html"
        detail_fixture = FIXTURES / "british_showjumping_detail.html"

        calendar_resp = _mock_response(calendar_fixture)
        detail_resp = _mock_response(detail_fixture)

        # Empty calendar page (no matching rows) ends pagination
        empty_page = _mock_response("<html><body><table><tbody></tbody></table></body></html>")

        mock_client = AsyncMock()
        calendar_call_count = 0

        async def mock_get(url, **kwargs):
            nonlocal calendar_call_count
            if "show-calendar" in url:
                calendar_call_count += 1
                # First call returns the fixture; second call returns empty to stop pagination
                if calendar_call_count == 1:
                    return calendar_resp
                return empty_page
            if "centre-detail" in url:
                return detail_resp
            return empty_page

        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.bases.httpx.AsyncClient", return_value=mock_client):
            parser = BritishShowjumpingParser()
            result = await parser.fetch_and_parse(
                "https://www.britishshowjumping.co.uk/show-calendar.cfm"
            )

        assert len(result) >= 1
        # All results should be show jumping
        for comp in result:
            assert comp.discipline == "Show Jumping"
            assert isinstance(comp, ExtractedCompetition)


# ---------------------------------------------------------------------------
# Abbey Farm Equestrian (Tribe Events / The Events Calendar)
# ---------------------------------------------------------------------------
class TestAbbeyFarmParser:
    @pytest.mark.asyncio
    async def test_extracts_all_events(self):
        """All events are captured — competitions and training/hire alike."""
        from app.parsers.abbey_farm import AbbeyFarmParser

        fixture = FIXTURES / "abbey_farm_events.json"
        mock_resp = _mock_response(fixture)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.bases.httpx.AsyncClient", return_value=mock_client):
            parser = AbbeyFarmParser()
            result = await parser.fetch_and_parse("https://abbeyfarmequestrian.co.uk/events/list/")

        # All 4 events captured (2 competitions + 1 clinic + 1 arena hire)
        assert len(result) == 4

        sj = result[0]
        assert sj.name == "Spring Show Jumping Show"
        assert sj.date_start == "2026-03-15"
        assert sj.venue_name == "Abbey Farm Equestrian"
        assert sj.venue_postcode == "DE4 2GL"
        # Parser doesn't set discipline — classification happens in scanner
        assert sj.discipline is None

        dressage = result[2]
        assert dressage.name == "Spring Dressage Show"
        assert dressage.date_start == "2026-04-05"
        assert dressage.discipline is None

    @pytest.mark.asyncio
    async def test_clinic_captured(self):
        """The Maddy Moffet clinic is captured (classification happens in scanner)."""
        from app.parsers.abbey_farm import AbbeyFarmParser

        fixture = FIXTURES / "abbey_farm_events.json"
        mock_resp = _mock_response(fixture)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.bases.httpx.AsyncClient", return_value=mock_client):
            parser = AbbeyFarmParser()
            result = await parser.fetch_and_parse("https://abbeyfarmequestrian.co.uk/events/list/")

        names = [r.name for r in result]
        assert "Maddy Moffet Polework Training Clinic" in names

        clinic = next(r for r in result if "Maddy Moffet" in r.name)
        assert clinic.venue_name == "Abbey Farm Equestrian"
        assert clinic.date_start == "2026-03-20"

    @pytest.mark.asyncio
    async def test_arena_hire_captured(self):
        """Arena hire is captured (classification happens in scanner)."""
        from app.parsers.abbey_farm import AbbeyFarmParser

        fixture = FIXTURES / "abbey_farm_events.json"
        mock_resp = _mock_response(fixture)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.bases.httpx.AsyncClient", return_value=mock_client):
            parser = AbbeyFarmParser()
            result = await parser.fetch_and_parse("https://abbeyfarmequestrian.co.uk/events/list/")

        names = [r.name for r in result]
        assert "Indoor Arena Hire" in names


# ---------------------------------------------------------------------------
# Venue normalisation tests
# ---------------------------------------------------------------------------
class TestNormaliseVenueName:
    """Test venue name normalisation including aliases and suffix stripping."""

    def setup_method(self):
        from app.parsers.utils import normalise_venue_name
        self.norm = normalise_venue_name

    # --- Postcode stripping ---

    def test_strips_trailing_postcode(self):
        assert self.norm("The Crescent GL6 7NP") == "The Crescent"

    def test_strips_postcode_in_parentheses(self):
        assert self.norm("Manor Farm (SO51 6EG)") == "Manor Farm"

    def test_strips_postcode_with_trailing_punctuation(self):
        assert self.norm("Wards Hill Farm Landshire Lane, Henstridge, BA8 0SD.") == "Wards Hill Farm Landshire Lane, Henstridge"

    def test_postcode_as_venue_name_becomes_tbc(self):
        # Postcodes as venue names are junk data — normalise to "Tbc"
        assert self.norm("CF71 7RQ") == "Tbc"

    # --- Suffix stripping ---

    def test_strips_ec_suffix(self):
        assert self.norm("Kelsall Hill EC") == "Kelsall Hill"

    def test_strips_e_c_suffix(self):
        assert self.norm("Kings Sedgemoor E C") == "Kings Sedgemoor"

    def test_strips_ecc_suffix(self):
        assert self.norm("Port Royal ECC") == "Port Royal"

    def test_strips_show_centre_suffix(self):
        assert self.norm("Duckhurst Farm Show Centre") == "Duckhurst Farm"

    def test_strips_equestrian_centre(self):
        assert self.norm("Hartpury Equestrian Centre") == "Hartpury"

    # --- Aliases no longer applied by normalise_venue_name (now handled by venue matcher) ---

    def test_alias_not_applied_hickstead(self):
        # normalise_venue_name no longer resolves aliases — that's the matcher's job
        assert self.norm("All England Show Jumping Course") == "All England Show Jumping Course"

    def test_alias_not_applied_oatridge(self):
        assert self.norm("The Scottish National") == "The Scottish National"

    def test_alias_not_applied_greenlands(self):
        # "Greenlands Arenas" doesn't match any suffix, so stays as-is
        assert self.norm("Greenlands Arenas") == "Greenlands Arenas"

    def test_suffix_stripping_still_works(self):
        # Suffix stripping still works (e.g. "Hartpury Equestrian Centre" -> "Hartpury")
        assert self.norm("Hartpury Equestrian Centre") == "Hartpury"

    # --- Unchanged names ---

    def test_simple_name_unchanged(self):
        assert self.norm("Hickstead") == "Hickstead"

    def test_already_canonical(self):
        assert self.norm("Oatridge") == "Oatridge"


# ── My Riding Life postcode extraction ──────────────────────────────


class TestMyRidingLifePostcode:
    """Verify the MRL parser extracts postcodes from location cells correctly."""

    def _parse(self, location_html):
        """Build a minimal MRL table row and parse it."""
        from app.parsers.my_riding_life import MyRidingLifeParser

        html = f"""<table><tr>
            <td>Actions</td>
            <td>Test Event</td>
            <td>01/06/2026</td>
            <td>01/06/2026</td>
            <td>Dressage</td>
            <td>{location_html}</td>
            <td>County</td>
            <td>10</td>
        </tr></table>"""
        parser = MyRidingLifeParser.__new__(MyRidingLifeParser)
        parser.source_key = "my_riding_life"
        results = parser._parse_page(html)
        return results[0] if results else None

    def test_postcode_with_space(self):
        comp = self._parse("Swallowfield Equestrian (B94 6JD)")
        assert comp is not None
        assert comp.venue_postcode == "B94 6JD"
        assert comp.venue_name == "Swallowfield Equestrian"

    def test_postcode_without_space(self):
        """Postcodes from MRL often arrive without space (e.g. B946JD)."""
        comp = self._parse("Swallowfield Equestrian(B946JD)")
        assert comp is not None
        assert comp.venue_postcode == "B94 6JD"  # normalised
        assert "B946JD" not in comp.venue_name

    def test_no_postcode(self):
        comp = self._parse("Some Venue Name")
        assert comp is not None
        assert comp.venue_postcode is None
        assert comp.venue_name == "Some Venue Name"

    def test_uk_location_fallback(self):
        """'UK Location' should fall back to org name extraction from event name."""
        comp = self._parse("UK Location")
        assert comp is not None
        assert comp.venue_name == "Test Event"  # falls back to event name

    def test_discipline_passed_as_raw_hint(self):
        """Parser passes raw discipline column text as hint — classifier normalises later."""
        comp = self._parse("Swallowfield Equestrian (B94 6JD)")
        assert comp is not None
        # _parse helper hardcodes "Dressage" in column 5
        assert comp.discipline == "Dressage"

    def test_empty_discipline_becomes_none(self):
        """Empty discipline column should result in discipline=None."""
        from app.parsers.my_riding_life import MyRidingLifeParser

        html = """<table><tr>
            <td>Actions</td>
            <td>Fun Ride</td>
            <td>01/06/2026</td>
            <td>01/06/2026</td>
            <td></td>
            <td>Some Venue (B94 6JD)</td>
            <td>County</td>
            <td>10</td>
        </tr></table>"""
        parser = MyRidingLifeParser.__new__(MyRidingLifeParser)
        parser.source_key = "my_riding_life"
        results = parser._parse_page(html)
        assert len(results) == 1
        assert results[0].discipline is None
