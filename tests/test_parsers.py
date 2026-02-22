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

        with patch("app.parsers.british_eventing.httpx.AsyncClient", return_value=mock_client):
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
        assert tweseldown.has_pony_classes is True  # "Junior" in classes

    @pytest.mark.asyncio
    async def test_skips_cancelled_events(self):
        from app.parsers.british_eventing import BritishEventingParser

        fixture = FIXTURES / "british_eventing_events.html"
        mock_resp = _mock_response(fixture)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.parsers.british_eventing.httpx.AsyncClient", return_value=mock_client):
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
        start, end = self.parser._parse_date("15 Mar 26")
        assert start == "2026-03-15"
        assert end is None

    def test_same_month_range(self):
        start, end = self.parser._parse_date("28 - 29 Mar 26")
        assert start == "2026-03-28"
        assert end == "2026-03-29"

    def test_cross_month_range(self):
        start, end = self.parser._parse_date("28 Feb - 1 Mar 26")
        assert start == "2026-02-28"
        assert end == "2026-03-01"

    def test_invalid_date(self):
        start, end = self.parser._parse_date("not a date")
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

        with patch("app.parsers.equipe_online.httpx.AsyncClient", return_value=mock_client):
            parser = EquipeOnlineParser()
            result = await parser.fetch_and_parse("https://online.equipe.com")

        # Should exclude the FRA event; only GBR events with extractable venues
        assert all(isinstance(r, ExtractedCompetition) for r in result)
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

        with patch("app.parsers.equipe_online.httpx.AsyncClient", return_value=mock_client):
            parser = EquipeOnlineParser()
            result = await parser.fetch_and_parse("https://online.equipe.com")

        # Check disciplines are mapped correctly for events that have extractable venues
        disciplines = {r.name: r.discipline for r in result}
        for name, disc in disciplines.items():
            assert disc is not None, f"Missing discipline for {name}"


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

        with patch("app.parsers.horse_monkey.httpx.AsyncClient", return_value=mock_client):
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

        with patch("app.parsers.horse_monkey.httpx.AsyncClient", return_value=mock_client):
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

        with patch("app.parsers.pony_club.httpx.AsyncClient", return_value=mock_client):
            parser = PonyClubParser()
            result = await parser.fetch_and_parse("https://pcuk.org/calendar/")

        assert len(result) == 2

        sj = result[0]
        assert sj.name == "East Midlands Area: Area Show Jumping"
        assert sj.date_start == "2026-03-15"
        assert sj.venue_name == "Keysoe"
        assert sj.has_pony_classes is True  # always True for PC

        dressage = result[1]
        assert dressage.venue_name == "Bicton Arena"
        assert dressage.has_pony_classes is True


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

        with patch("app.parsers.british_showjumping.httpx.AsyncClient", return_value=mock_client):
            parser = BritishShowjumpingParser()
            result = await parser.fetch_and_parse(
                "https://www.britishshowjumping.co.uk/show-calendar.cfm"
            )

        assert len(result) >= 1
        # All results should be show jumping
        for comp in result:
            assert comp.discipline == "Show Jumping"
            assert isinstance(comp, ExtractedCompetition)
