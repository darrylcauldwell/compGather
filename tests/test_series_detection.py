"""Precision-gated series / BS-class / tier detection in extract_tags.

Series and tier are read from the event text; BS classes (ladder + audience +
height) are read PER CLASS from the class list using BS's real vocabulary
(Pony/Senior Foxhunter, Pony Newcomers, …) — not rider terms like "Junior
Foxhunter", which BS doesn't use.
"""

from app.services.tag_manager import extract_tags, serialize_tags


def _tags(name: str, description: str = "", classes: list[str] | None = None) -> list[str]:
    return extract_tags(name=name, description=description, classes=classes, event_type="competition")


class TestNamedSeries:
    def test_trailblazers_from_class_text(self):
        tags = _tags("Unaffiliated Show Jumping", "Class 8: Trailblazers Qualifier")
        assert "series:trailblazers" in tags
        assert "special:qualifier" in tags

    def test_cricklands_excludes_south_view(self):
        assert "series:cricklands" in _tags("Cricklands Qualifier Show Jumping")
        assert "series:cricklands" not in _tags("South View Cricklands Open")

    def test_sunshine_tour_uk_disambiguation(self):
        assert "series:sunshine-tour-uk" in _tags("Sunshine Tour Qualifier")
        assert "series:sunshine-tour-uk" not in _tags("CSI3* Sunshine Tour")


class TestBSClassLadder:
    def test_pony_foxhunter_is_the_junior_tier(self):
        tags = _tags("BS Junior Show Jumping - Venue", classes=["STX-UK Pony Foxhunter First Round"])
        assert "class:pony-foxhunter" in tags
        assert "class:foxhunter" not in tags          # pony variant wins, not the bare class
        assert "audience:pony" in tags
        assert "height:110" in tags                    # canonical Pony Foxhunter height

    def test_senior_foxhunter_folds_into_foxhunter(self):
        tags = _tags("BS Senior Show Jumping", classes=["Redpost Senior Foxhunter First Round"])
        assert "class:foxhunter" in tags
        assert "class:senior-foxhunter" not in tags    # retired — folded to foxhunter + audience
        assert "audience:senior" in tags
        assert "height:120" in tags

    def test_newcomers_undeferred(self):
        tags = _tags("BS Junior Show Jumping", classes=["Pony Newcomers First Round"])
        assert "class:pony-newcomers" in tags
        assert "audience:pony" in tags

    def test_british_novice(self):
        assert "class:british-novice" in _tags("BS Show", classes=["Ariat Senior British Novice First Round"])

    def test_junior_foxhunter_retired(self):
        # BS doesn't use this term; even if a class said it, the slug isn't emitted.
        assert "class:junior-foxhunter" not in _tags("BS Show", classes=["Junior Foxhunter"])

    def test_explicit_height_from_class_name(self):
        tags = _tags("BS Senior Show Jumping", classes=["Senior 90cm Open"])
        assert "height:90" in tags
        assert "audience:senior" in tags
        assert not any(t.startswith("class:") for t in tags)  # not a graded ladder class

    def test_no_classes_no_class_tags(self):
        tags = _tags("BS Senior Show Jumping - Venue")
        assert not any(t.startswith(("class:", "audience:", "height:")) for t in tags)


class TestBSCategory:
    def test_category_from_show_name(self):
        assert "category:junior" in _tags("BS Junior Show Jumping - Venue")
        assert "category:senior" in _tags("BS Senior Show Jumping - Venue")
        assert "category:club" in _tags("BS Club Show Jumping - Venue")

    def test_junior_and_club(self):
        tags = _tags("BS Junior & Club Show Jumping - Venue")
        assert "category:junior" in tags and "category:club" in tags


class TestTier:
    def test_elite_from_international_code_or_star(self):
        assert "tier:elite" in _tags("CSI3* Grand Prix")
        assert "tier:elite" in _tags("Longines Global Champions Tour")

    def test_unaffiliated(self):
        assert "tier:unaffiliated" in _tags("Unaffiliated Show Jumping")

    def test_at_most_one_tier_and_elite_wins(self):
        tags = _tags("British Showjumping CSI3* International")
        assert [t for t in tags if t.startswith("tier:")] == ["tier:elite"]


class TestVocabulary:
    def test_new_namespaces_validate(self):
        # serialize_tags raises on any tag outside VALID_TAGS.
        serialize_tags([
            "class:pony-foxhunter", "class:foxhunter", "class:newcomers", "class:british-novice",
            "audience:pony", "audience:senior", "category:junior", "category:club",
            "height:90", "height:110", "height:120", "special:qualifier",
        ])
