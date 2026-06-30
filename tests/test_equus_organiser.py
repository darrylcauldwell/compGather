"""Equus Organiser parser — offline parsing tests (the live fetch needs Playwright).

Exercises the GetEventPartial card parsing, date handling, dedup, and the
data-driven venue registration.
"""

from app.parsers.equus_organiser import EQUUS_VENUES
from app.parsers.nvec import NVECParser
from app.parsers.registry import get_parser

# Mirrors the server-rendered GetEventPartial HTML (.box cards).
FIXTURE = """
<div class="box">
  <span class="eventName">Friday Night Summer SJ League - ESUK qualifier</span>
  <span class="eventDate">Friday 3rd July 2026</span>
  <span class="eventType">Show Jumping</span>
</div>
<div class="box">
  <span class="eventName">Unaffiliated Dressage</span>
  <span class="eventDate">Sunday 5th July 2026</span>
</div>
<div class="box">
  <span class="eventName">Duplicate</span>
  <span class="eventDate">Friday 3rd July 2026</span>
</div>
<div class="box">
  <span class="eventName">Duplicate</span>
  <span class="eventDate">Friday 3rd July 2026</span>
</div>
<div class="box"><span class="eventName">No date here</span></div>
"""


class TestParse:
    def _events(self):
        return NVECParser()._parse_event_html(FIXTURE)

    def test_extracts_cards_with_dates(self):
        evs = self._events()
        # 2 distinct dated events (the duplicate collapses, the date-less card skipped)
        assert len(evs) == 3
        names = [e.name for e in evs]
        assert "Friday Night Summer SJ League - ESUK qualifier" in names
        assert "No date here" not in names

    def test_date_and_fields(self):
        ev = next(e for e in self._events() if e.name.startswith("Friday Night"))
        assert ev.date_start == "2026-07-03"
        assert ev.discipline == "Show Jumping"
        assert ev.venue_name == "Newbold Verdon Equestrian Centre"
        assert ev.venue_postcode == "LE9 9NE"

    def test_missing_event_type_is_none(self):
        ev = next(e for e in self._events() if e.name == "Unaffiliated Dressage")
        assert ev.date_start == "2026-07-05"
        assert ev.discipline is None

    def test_dedup(self):
        dupes = [e for e in self._events() if e.name == "Duplicate"]
        assert len(dupes) == 1


class TestRegistration:
    def test_all_equus_venues_registered(self):
        for c in EQUUS_VENUES:
            parser = get_parser(c["key"])
            assert parser.SUBDOMAIN == c["subdomain"]
            assert parser.VENUE_NAME == c["venue_name"]

    def test_nvec_uses_the_base(self):
        assert isinstance(get_parser("nvec"), NVECParser)
        assert get_parser("nvec").hub_url == "https://nvec.equusorganiser.com/"
