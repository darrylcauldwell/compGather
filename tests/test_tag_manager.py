"""Tests for event tag extraction (app/services/tag_manager.py).

Covers the word-boundary matching rewrite: regression cases for the substring
false-positives/negatives found in the tag-logic audit, the discipline single-
source-of-truth contract, vocabulary sync with the seed data, and display names.
"""

from __future__ import annotations

import pytest

from app.seed_data import get_discipline_seeds
from app.services.tag_manager import (
    VALID_TAGS,
    deserialize_tags,
    extract_tags,
    get_tag_display_name,
    serialize_tags,
    validate_tag,
)


def _tags(name, **kw):
    return set(extract_tags(name, **kw))


# --- Regression cases: tag must be PRESENT --------------------------------
@pytest.mark.parametrize("name,kwargs,expected", [
    ("International Horse Show", {}, "scope:international"),
    ("Al Shira'aa International Horse Show 2026", {"discipline": "Show Jumping"}, "discipline:show-jumping"),
    ("Dressage Championships - Hartpury", {"discipline": "Dressage"}, "level:championship"),
    ("FEI World Championships Aachen", {}, "level:championship"),
    ("Advanced Medium Dressage", {"discipline": "Dressage"}, "level:advanced"),
    ("Mountain & Moorland In-Hand", {}, "special:mountain-and-moorland"),
    ("Native Breeds Show", {}, "special:native-breed"),
    ("Area Qualifiers", {}, "special:qualifier"),
    ("Senior Members Dressage", {"discipline": "Dressage"}, "age:senior"),
    ("Team Chase", {}, "format:team"),
])
def test_tag_present(name, kwargs, expected):
    assert expected in _tags(name, **kwargs)


# --- Regression cases: tag must be ABSENT (former false positives) --------
@pytest.mark.parametrize("name,kwargs,forbidden", [
    ("International Horse Show", {}, "scope:national"),          # 'national' in 'international'
    ("Herbs Workshop", {}, "discipline:show-jumping"),           # 'bs ' mid-word
    ("Lambs BD Sale", {}, "discipline:dressage"),                # 'bd ' mid-word (discipline)
    ("Advanced Booking Required", {}, "level:advanced"),         # admin phrasing
    ("Beach Polocrosse", {"discipline": "Polocrosse"}, "discipline:polo"),  # ' polo' in 'polocrosse'
    ("Senior Citizens Fun Day", {}, "age:senior"),               # non-rider 'senior'
    ("National Trust Open Day", {}, "scope:national"),           # proper noun
    ("Grand Prix", {}, "level:championship"),                    # grade != championship
    ("Triathlon Challenge", {}, "discipline:tetrathlon"),        # distinct sport
])
def test_tag_absent(name, kwargs, forbidden):
    assert forbidden not in _tags(name, **kwargs)


def test_championship_is_level_only_not_scope():
    tags = _tags("National Championship Final", discipline="Dressage")
    assert "level:championship" in tags
    assert "scope:championship" not in tags  # 'championship' removed from scope vocabulary
    assert not validate_tag("scope:championship")


def test_type_always_present_and_single():
    tags = extract_tags("Anything At All")
    type_tags = [t for t in tags if t.startswith("type:")]
    assert type_tags == ["type:competition"]
    assert "type:training" in extract_tags("X", event_type="training")
    assert "type:venue-hire" in extract_tags("X", event_type="venue_hire")


def test_polocrosse_single_discipline():
    # Discipline comes solely from the classifier column -> exactly one tag.
    disc = [t for t in extract_tags("Beach Polocrosse", discipline="Polocrosse")
            if t.startswith("discipline:")]
    assert disc == ["discipline:polocrosse"]


# --- Discipline single-source-of-truth + seed sync (guards silent drift) ---
@pytest.mark.parametrize("canonical", sorted(get_discipline_seeds().keys()))
def test_every_seed_discipline_round_trips(canonical):
    """Each canonical discipline yields a valid tag whose display name is the
    canonical again — so badge == column == filter for every discipline."""
    tags = extract_tags("Event", discipline=canonical)
    disc = [t for t in tags if t.startswith("discipline:")]
    assert len(disc) == 1, f"{canonical} produced {disc}"
    assert validate_tag(disc[0])
    assert get_tag_display_name(disc[0]) == canonical


def test_discipline_vocabulary_matches_seeds():
    expected = {d.lower().replace(" ", "-") for d in get_discipline_seeds()}
    assert set(VALID_TAGS["discipline"]) == expected


def test_unknown_discipline_yields_no_discipline_tag():
    tags = extract_tags("Event", discipline="Underwater Polo")
    assert not [t for t in tags if t.startswith("discipline:")]


# --- Display names ---------------------------------------------------------
@pytest.mark.parametrize("tag,expected", [
    ("affiliation:bsps", "BSPS"),
    ("affiliation:bsha", "BSHA"),
    ("affiliation:endurance-gb", "Endurance GB"),
    ("affiliation:hpa-polo", "HPA Polo"),
    ("affiliation:british-dressage", "British Dressage"),
    ("discipline:show-jumping", "Show Jumping"),
    ("level:novice", "Novice"),
])
def test_display_name(tag, expected):
    assert get_tag_display_name(tag) == expected


# --- Serialization plumbing ------------------------------------------------
def test_serialize_round_trip():
    tags = ["discipline:dressage", "type:competition"]
    assert deserialize_tags(serialize_tags(tags)) == tags
    assert serialize_tags([]) is None
    assert deserialize_tags(None) == []


def test_serialize_rejects_invalid():
    with pytest.raises(ValueError):
        serialize_tags(["bogus:value"])


def test_extract_only_emits_valid_tags():
    # Across a varied corpus, every emitted tag must be in the vocabulary.
    corpus = [
        "Spring Dressage Championships", "Arena Hire Saturday", "Pony Club Camp",
        "CSIO Barcelona", "Working Hunter Pony Final", "Endurance Ride 100km",
        "Unaffiliated Show Jumping", "Mountain & Moorland In-Hand Qualifier",
    ]
    for name in corpus:
        for tag in extract_tags(name, discipline="Dressage", event_type="show"):
            assert validate_tag(tag), f"{name} produced invalid {tag}"
