"""Dual-axis classification for continental venues.

Big continental venues run mixed-tier fixtures (enterable youth/1*/YH classes
alongside elite CSI/CDI). event_type must be decided per event so junior/amateur
classes land in Compete while purely-elite fixtures stay Watch-only.
"""

from app.parsers.utils import (
    continental_discipline,
    continental_event_type,
    prefix_venue,
)
from app.services.event_classifier import EventClassifier, classify_spectator


def _tabs(name: str) -> set[str]:
    """Replicate the scanner: hint -> classify -> spectator -> tab membership."""
    _, event_type = EventClassifier.classify(name, event_type_hint=continental_event_type(name))
    spectator = classify_spectator(name, event_type)
    tabs = set()
    if event_type == "competition":
        tabs.add("Compete")
    if spectator:
        tabs.add("Watch")
    return tabs


class TestEnterableTiers:
    """Entry-level markers => enterable (Compete), and Watch too when starred."""

    def test_youth_classes_are_enterable(self):
        # The exact Sentower fixture the user's daughter could enter.
        assert continental_event_type("CSI Youth (J/P/Ch & U25) + 1* + YH") == "competition"

    def test_mixed_tier_with_elite_still_enterable(self):
        # 3* alongside 1*/YH: enterable markers win.
        assert continental_event_type("CSI 3* / 1* / YH") == "competition"
        assert _tabs("CSI 3* / 1* / YH") == {"Compete", "Watch"}

    def test_amateur_tour_week(self):
        assert continental_event_type("SUMMER TOUR CSI2*1*YH LIER") == "competition"

    def test_talent_search(self):
        assert continental_event_type("Hunter Talent Search") == "competition"


class TestEliteTiers:
    """Purely-elite fixtures => Watch-only (show)."""

    def test_pure_high_star(self):
        assert continental_event_type("CDI 4* - Dressage") == "show"
        assert _tabs("CDI 4* - Dressage") == {"Watch"}

    def test_global_champions_tour_is_watch_only(self):
        # No CSI/star token, but elite wording must still reach Watch (not vanish).
        assert continental_event_type("Longines Global Champions Tour") == "show"
        assert _tabs("Longines Global Champions Tour") == {"Watch"}

    def test_national_a5_star(self):
        assert continental_event_type("Adriatic Tour — Nazionale A5*") == "show"
        assert _tabs("Adriatic Tour — Nazionale A5*") == {"Watch"}


class TestPlainCompetitions:
    """No tier markers => Compete only (a routine national comp)."""

    def test_plain_outdoor_competition(self):
        assert continental_event_type("Peelbergen Competition Outdoor") == "competition"
        assert _tabs("Peelbergen Competition Outdoor") == {"Compete"}

    def test_no_event_is_invisible(self):
        # Every continental fixture must appear in at least one tab.
        for name in [
            "CSI Youth (J/P/Ch & U25) + 1* + YH",
            "CDI 4* - Dressage",
            "Longines Global Champions Tour",
            "Adriatic Tour — Nazionale A5*",
            "Peelbergen Competition Outdoor",
            "GOLD + VOR JUMPING Finale Jonge paarden",
            "CSI**",
        ]:
            assert _tabs(name), f"{name!r} appears in no tab"


class TestDisciplineAndPrefix:
    def test_discipline_hint(self):
        assert continental_discipline("CDI 4* Dressage") == "Dressage"
        assert continental_discipline("CCI4*-L") == "Eventing"
        assert continental_discipline("CSI 2*") == "Show Jumping"
        assert continental_discipline("GOLD") == "Show Jumping"  # jumping venue default

    def test_prefix_venue(self):
        assert prefix_venue("Hunter Talent Search", "Peelbergen") == "Peelbergen — Hunter Talent Search"
        # Already names the venue -> unchanged.
        assert prefix_venue("Peelbergen Competition Outdoor", "Peelbergen") == "Peelbergen Competition Outdoor"
