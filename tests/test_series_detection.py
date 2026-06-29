"""Precision-gated series / class detection in extract_tags (slice 2).

Series and BS class signals are read from the full event text (name +
description + class list) but only emitted when distinctive — with require/
exclude rules to avoid the known false positives (South View ≠ Cricklands,
Spanish CSI ≠ UK Sunshine Tour, Junior Foxhunter ≠ bare Foxhunter).
"""

from app.services.tag_manager import extract_tags, serialize_tags


def _tags(name: str, description: str = "") -> list[str]:
    return extract_tags(name=name, description=description, event_type="competition")


class TestNamedSeries:
    def test_trailblazers_from_class_text(self):
        # Generic event title; the series lives in the class list.
        tags = _tags("Unaffiliated Show Jumping", "Class 8: Trailblazers Qualifier")
        assert "series:trailblazers" in tags
        assert "special:qualifier" in tags  # the qualifier stage flag still fires

    def test_blue_chip(self):
        assert "series:blue-chip" in _tags("Spring Show", "Class 6: Blue Chip Qualifier")

    def test_cricklands_excludes_south_view(self):
        assert "series:cricklands" in _tags("Cricklands Qualifier Show Jumping")
        # South View is the venue that hosts it — must NOT be tagged as the series.
        assert "series:cricklands" not in _tags("South View Cricklands Open")

    def test_sunshine_tour_uk_disambiguation(self):
        # UK grassroots: requires "qualifier", forbids "csi".
        assert "series:sunshine-tour-uk" in _tags("Sunshine Tour Qualifier")
        # Elite Spanish CSI must not match.
        assert "series:sunshine-tour-uk" not in _tags("CSI3* Sunshine Tour")
        # Bare "Sunshine Tour" without a qualifier shouldn't match either.
        assert "series:sunshine-tour-uk" not in _tags("Sunshine Tour Day")


class TestClassSeries:
    def test_junior_foxhunter_precedence(self):
        tags = _tags("Show Jumping", "Class 5: Junior Foxhunter")
        assert "class:junior-foxhunter" in tags
        assert "class:foxhunter" not in tags  # bare class suppressed when junior present

    def test_plain_foxhunter(self):
        tags = _tags("Show Jumping", "Class 7: Foxhunter 1.20m")
        assert "class:foxhunter" in tags

    def test_british_novice(self):
        assert "class:british-novice" in _tags("SJ", "Class 1: British Novice")

    def test_deferred_classes_not_emitted(self):
        # 'discovery'/'newcomers' are ambiguous bare words → deferred, must not tag.
        tags = _tags("Discovery Day Clinic", "Newcomers welcome")
        assert not any(t.startswith("class:") for t in tags)


class TestVocabulary:
    def test_series_and_class_tags_validate(self):
        # serialize_tags raises on any tag outside VALID_TAGS — proves the new
        # namespaces are registered.
        serialize_tags([
            "series:trailblazers", "series:cricklands", "series:bs-club",
            "series:blue-chip", "class:foxhunter", "class:junior-foxhunter",
            "class:british-novice", "special:qualifier",
        ])
