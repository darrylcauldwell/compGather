"""GC Global Champions (Longines GCT/GCL) parser — offline parsing tests.

The live fetch needs Playwright; here we exercise the HTML parsing, the
same-month/cross-month date logic, the city extraction, the Riesenbeck skip
(owned by the dedicated venue parser), and that every leg is Watch-only.
"""

from app.parsers.gc_global_champions import GCGlobalChampionsParser
from app.services.event_classifier import EventClassifier, classify_spectator

# Mirrors the rendered grid: marquee legs carry a /schedule/2026/<slug>/ link;
# back-half legs are plain "DD - DD Month City Tickets" text (incl. a cross-month
# range and the Riesenbeck leg that must be skipped).
FIXTURE = """
<html><body>
  <div><a href="/en-us/schedule/2026/doha/city-venue">
     <span>4 - 7 March</span><span>Doha</span> City &amp; Location</a></div>
  <div><a href="/en-us/schedule/2026/mexico-city/citylocation">
     <span>16 - 19 April</span><span>Mexico City</span> City &amp; Location</a></div>
  <div><a href="/en-us/schedule/2026/london/city-and-location">
     <span>7 - 9 August</span><span>London</span> City &amp; Location Tickets</a></div>
  <p>16 - 19 July Riesenbeck Tickets
     4 - 6 September Valkenswaard Tickets
     9 - 11 October Rome Tickets
     30 October - 1 November Rabat Tickets
     18 - 21 November Riyadh Tickets</p>
</body></html>
"""


def _legs():
    return GCGlobalChampionsParser()._parse(FIXTURE)


class TestParse:
    def test_extracts_all_real_legs(self):
        legs = _legs()
        cities = {e.venue_name for e in legs}
        # Doha, Mexico City, London (linked) + Valkenswaard, Rome, Rabat, Riyadh (text)
        assert cities == {"Doha", "Mexico City", "London", "Valkenswaard", "Rome", "Rabat", "Riyadh"}

    def test_riesenbeck_leg_skipped(self):
        # The dedicated Riesenbeck venue parser owns this fixture; avoid a dup.
        assert all("riesenbeck" not in e.venue_name.lower() for e in _legs())

    def test_clean_city_name_from_slug(self):
        # "mexico-city" slug must not be mangled by the "City & Location" label.
        assert any(e.venue_name == "Mexico City" for e in _legs())

    def test_same_month_range(self):
        doha = next(e for e in _legs() if e.venue_name == "Doha")
        assert doha.date_start == "2026-03-04"
        assert doha.date_end == "2026-03-07"

    def test_cross_month_range(self):
        rabat = next(e for e in _legs() if e.venue_name == "Rabat")
        assert rabat.date_start == "2026-10-30"
        assert rabat.date_end == "2026-11-01"

    def test_name_and_discipline(self):
        rome = next(e for e in _legs() if e.venue_name == "Rome")
        assert rome.name == "Longines Global Champions Tour — Rome"
        assert rome.discipline == "Show Jumping"


class TestClassification:
    def test_every_leg_is_watch_only(self):
        for e in _legs():
            _, et = EventClassifier.classify(e.name, event_type_hint=e.event_type)
            assert et == "show"
            assert classify_spectator(e.name, et) is True


def test_empty_html_is_safe():
    assert GCGlobalChampionsParser()._parse("<html><body></body></html>") == []
