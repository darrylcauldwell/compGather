"""Multi-discipline detection in extract_tags.

NSEA-style fixtures run several disciplines at one event (e.g. "DR, Combined
Training and SJ Qualifiers"). extract_tags emits a discipline: tag for each so
the discipline filter surfaces the event under every discipline it offers.
"""

from app.services.tag_manager import discipline_tag_slug, extract_tags


def _disciplines(name: str, classes: list[str] | None = None, discipline: str | None = None) -> set[str]:
    tags = extract_tags(name=name, classes=classes, discipline=discipline, event_type="competition")
    return {t for t in tags if t.startswith("discipline:")}


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
