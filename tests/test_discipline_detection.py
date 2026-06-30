"""Multi-discipline detection in extract_tags.

NSEA-style fixtures run several disciplines at one event (e.g. "DR, Combined
Training and SJ Qualifiers"). extract_tags emits a discipline: tag for each so
the discipline filter surfaces the event under every discipline it offers.
"""

from app.services.event_classifier import EventClassifier
from app.services.tag_manager import discipline_tag_slug, extract_tags


def _disciplines(
    name: str,
    classes: list[str] | None = None,
    discipline: str | None = None,
    source_affiliation: str | None = None,
    venue_name: str | None = None,
) -> set[str]:
    tags = extract_tags(
        name=name, classes=classes, discipline=discipline,
        event_type="competition", source_affiliation=source_affiliation,
        venue_name=venue_name,
    )
    return {t for t in tags if t.startswith("discipline:")}


class TestVenueLeakage:
    def test_discipline_word_in_venue_not_tagged(self):
        # "Polo" is in the venue, not the competition — must not become a discipline.
        d = _disciplines(
            "BS Senior Show Jumping - Dallas Burston Polo Club",
            discipline="Show Jumping", venue_name="Dallas Burston Polo Club",
        )
        assert "discipline:polo" not in d
        assert "discipline:show-jumping" in d


class TestClassifierPrimary:
    def test_arena_eventing_beats_eventing(self):
        # Longest matching alias wins: "arena eventing" over "eventing".
        disc, _ = EventClassifier.classify("Inside and out Arena Eventing")
        assert disc == "Arena Eventing"


class TestMultiDiscipline:
    def test_epworth_nsea_three_disciplines(self):
        # The exact case the user reported.
        d = _disciplines("DR, Combined Training and SJ Qualifiers @ Epworth")
        assert d == {"discipline:dressage", "discipline:combined-training", "discipline:show-jumping"}

    def test_abbreviations_dr_ct_sj(self):
        d = _disciplines("DR, CT and SJ")
        assert d == {"discipline:dressage", "discipline:combined-training", "discipline:show-jumping"}

    def test_classes_contribute_disciplines(self):
        d = _disciplines("NSEA Qualifiers", classes=["Intro Dressage", "80cm Show Jumping"])
        assert "discipline:dressage" in d
        assert "discipline:show-jumping" in d


class TestNamedFormats:
    """NSEA / riding-club formats that map to an existing discipline by alias."""

    def test_jumping_with_style_is_own_discipline(self):
        # JwS is a distinct NSEA discipline (style-judged jumping), NOT show jumping.
        assert "discipline:jumping-with-style" in _disciplines("NSEA Jumping With Style Qualifier")
        assert "discipline:jumping-with-style" in _disciplines("JwS CHQ @ South View")
        assert "discipline:show-jumping" not in _disciplines("JwS CHQ @ South View")

    def test_eventer_challenge_is_own_discipline(self):
        # Spelled-out form, via the normal alias scan (no NSEA context needed).
        d = _disciplines("Mini Eventer Challenge @ Highfields")
        assert "discipline:eventers-challenge" in d
        assert "discipline:eventing" not in d

    def test_ec_abbreviation_only_in_nsea_context_before_venue(self):
        # NSEA + "EC" before the @ venue → Eventers Challenge.
        assert "discipline:eventers-challenge" in _disciplines("EC Qualifiers @ Greenlands", source_affiliation="nsea")
        assert "discipline:eventers-challenge" in _disciplines("NSEA EC Champs @ Hickstead")
        # "EC" after the @ is the venue (Equestrian Centre) — must NOT match.
        assert "discipline:eventers-challenge" not in _disciplines("Grass Roots SJ @ Beechwood EC", source_affiliation="nsea")
        # Not NSEA → "EC" is always the venue.
        assert "discipline:eventers-challenge" not in _disciplines("BS Show Jumping @ Bury Farm EC")

    def test_combined_challenge_is_combined_training(self):
        assert "discipline:combined-training" in _disciplines("Combined Challenge Qualifier")


class TestNoFalsePositives:
    def test_single_discipline_stays_single(self):
        assert _disciplines("Unaffiliated Show Jumping") == {"discipline:show-jumping"}

    def test_dr_does_not_match_inside_words(self):
        # "dr" is word-boundary anchored: "Drag Hunt" must not become Dressage.
        d = _disciplines("Drag Hunt")
        assert "discipline:dressage" not in d
        assert "discipline:drag-hunt" in d

    def test_nested_alias_does_not_double_tag(self):
        # "arena eventing" claims its span so bare "eventing" can't also match it.
        assert _disciplines("Arena Eventing") == {"discipline:arena-eventing"}


class TestPrimaryAlwaysIncluded:
    def test_classifier_discipline_included_even_if_not_in_name(self):
        # The column's discipline is always tagged, even when the title omits it.
        d = _disciplines("Summer Festival", discipline="Eventing")
        assert "discipline:eventing" in d


class TestDisciplineTagSlug:
    def test_known_discipline(self):
        assert discipline_tag_slug("Combined Training") == "combined-training"
        assert discipline_tag_slug("Show Jumping") == "show-jumping"

    def test_unknown_returns_none(self):
        assert discipline_tag_slug("Quidditch") is None
