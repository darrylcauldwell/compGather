"""Tag management for event classification.

Tags are derived per event and stored as a JSON array on Competition.tags, e.g.
["discipline:dressage", "type:competition", "affiliation:british-dressage"].

Matching uses WORD BOUNDARIES (\\b regex), not naive substring containment, so
"International" no longer matches "national", "Herbs Workshop" is not tagged
show-jumping, etc. Discipline is taken from the classifier's canonical result
(the same value stored in Competition.discipline) so the badge, the column and
the filter never disagree.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.seed_data import get_discipline_seeds


def _slug(name: str) -> str:
    """Canonical discipline name -> tag slug, e.g. 'Show Jumping' -> 'show-jumping'."""
    return name.lower().replace(" ", "-")


# Discipline vocabulary is DERIVED from the seed data (the documented single
# source of truth) so it can never drift out of sync with the classifier.
_DISCIPLINE_SLUGS = [_slug(d) for d in get_discipline_seeds()]


@lru_cache(maxsize=1)
def _series_seeds() -> dict:
    """Load the named-series / class taxonomy from app/series_seeds.json."""
    path = Path(__file__).resolve().parent.parent / "series_seeds.json"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _name_series_rules() -> dict:
    """Series detected from event text (name + description + class list),
    precision-gated. Excludes source/tag-detected and deferred entries."""
    return {
        k: r
        for k, r in _series_seeds().get("series", {}).items()
        if not k.startswith("_") and r.get("detect") == "name" and not r.get("deferred")
    }


def _class_series_rules() -> dict:
    """BS class series detected from text (excludes deferred / ambiguous ones)."""
    return {
        k: r
        for k, r in _series_seeds().get("class_series", {}).items()
        if not k.startswith("_") and not r.get("deferred")
    }


# Tag vocabularies for the two new namespaces (all non-meta keys are valid even
# if currently deferred from detection, so a future enable can't be rejected).
_SERIES_SLUGS = [
    k for k, r in _series_seeds().get("series", {}).items()
    if not k.startswith("_") and r.get("detect") == "name"
]
_CLASS_SLUGS = [k for k in _series_seeds().get("class_series", {}) if not k.startswith("_")]

# Canonical tag vocabulary
VALID_TAGS = {
    # Discipline (one, mirrors Competition.discipline; derived from seeds)
    "discipline": _DISCIPLINE_SLUGS,
    # Event type (exactly one, from the classifier)
    "type": ["competition", "training", "venue-hire", "show", "social", "other"],
    # Level (at most one)
    "level": ["beginner", "novice", "intermediate", "advanced", "championship", "mixed"],
    # Affiliation (zero or more)
    "affiliation": [
        "british-dressage", "british-showjumping", "british-eventing",
        "pony-club", "nsea", "endurance-gb", "unaffiliated",
        "bsps", "bsha", "british-horseball", "hpa-polo",
    ],
    # Format (zero or more)
    "format": ["team", "in-hand", "clinic", "workshop"],
    # Scope (at most one; strictly geographic)
    "scope": ["national", "international"],
    # Age group (zero or more)
    "age": ["junior", "young-rider", "adult", "senior"],
    # Special (zero or more)
    "special": [
        "qualifier", "invitational", "breed-specific",
        "mountain-and-moorland", "native-breed", "long-format",
    ],
    # Named series / pathways (zero or more; from series_seeds.json)
    "series": _SERIES_SLUGS,
    # BS class series (zero or more; from series_seeds.json)
    "class": _CLASS_SLUGS,
}


def validate_tag(tag: str) -> bool:
    """Check if a tag is valid (format: category:value)."""
    if not tag or ":" not in tag:
        return False
    category, value = tag.split(":", 1)
    return value in VALID_TAGS.get(category, [])


def serialize_tags(tags: list[str]) -> Optional[str]:
    """Convert list of tags to JSON string for storage."""
    if not tags:
        return None
    for tag in tags:
        if not validate_tag(tag):
            raise ValueError(f"Invalid tag: {tag}")
    return json.dumps(tags, sort_keys=False)


def deserialize_tags(tags_json: Optional[str]) -> list[str]:
    """Convert JSON string back to list of tags."""
    if not tags_json:
        return []
    try:
        tags = json.loads(tags_json)
        return tags if isinstance(tags, list) else []
    except json.JSONDecodeError:
        return []


# Map from DB event_type values to tag type values
_EVENT_TYPE_TO_TAG = {
    "competition": "competition",
    "training": "training",
    "venue_hire": "venue-hire",
    "show": "show",
    "social": "social",
    "other": "other",
}


@lru_cache(maxsize=1024)
def _pattern(keyword: str) -> "re.Pattern[str]":
    """Compiled whole-word/phrase matcher for a lowercase keyword.

    Simple alphabetic words (>=4 letters) also match their plural ('championship'
    -> 'championships'). Short codes and phrases match exactly.
    """
    suffix = r"s?\b" if (keyword.isalpha() and len(keyword) >= 4) else r"\b"
    return re.compile(r"\b" + re.escape(keyword) + suffix)


def _matches(text: str, keywords: list[str]) -> bool:
    """True if any keyword matches *text* on word boundaries."""
    return any(_pattern(kw).search(text) for kw in keywords)


def _normalise(name: str, description: str) -> str:
    """Lowercase, expand '&' to 'and', and collapse whitespace for matching."""
    combined = f"{name} {description}".lower().replace("&", " and ")
    return re.sub(r"\s+", " ", combined).strip()


def extract_tags(
    name: str,
    description: str = "",
    discipline: Optional[str] = None,
    event_type: str = "competition",
    source_affiliation: Optional[str] = None,
) -> list[str]:
    """Extract tags from an event.

    Discipline and type are authoritative inputs from EventClassifier (not
    re-derived from text here — that previously diverged from the stored column).
    Level/scope/affiliation/format/age/special are inferred from the event text
    using word-boundary matching.
    """
    tags: list[str] = []
    combined = _normalise(name, description)

    # 1. Discipline — single source of truth: the classifier's canonical result.
    if discipline:
        slug = _slug(discipline)
        if slug in VALID_TAGS["discipline"]:
            tags.append(f"discipline:{slug}")

    # 2. Event type — from the classifier, mapped to tag format.
    tags.append(f"type:{_EVENT_TYPE_TO_TAG.get(event_type, 'competition')}")

    # 3. Level (at most one; most significant first). 'advanced' must not be the
    # administrative "advanced booking/notice/entries".
    advanced = bool(re.search(r"\badvanced\b(?!\s+(?:booking|notice|entr))", combined))
    level_checks = [
        ("championship", lambda: _matches(combined, ["championship"])),
        ("advanced", lambda: advanced),
        ("intermediate", lambda: _matches(combined, ["intermediate"])),
        ("novice", lambda: _matches(combined, ["novice"])),
        ("beginner", lambda: _matches(combined, ["beginner"])),
        ("mixed", lambda: _matches(combined, ["all levels", "mixed level"])),
    ]
    for level, check in level_checks:
        if check():
            tags.append(f"level:{level}")
            break

    # 4. Affiliation (zero or more) from text, plus the source-level affiliation.
    affiliation_keywords = {
        "british-dressage": ["british dressage", "bd"],
        "british-showjumping": ["british showjumping", "bs area"],
        "british-eventing": ["british eventing"],
        "pony-club": ["pony club"],
        "nsea": ["nsea"],
        "endurance-gb": ["endurance gb"],
        "bsps": ["bsps", "british show pony"],
        "bsha": ["bsha", "british show horse"],
        "british-horseball": ["british horseball"],
        "hpa-polo": ["hpa polo"],
    }
    added_affiliations = set()
    for affiliation, keywords in affiliation_keywords.items():
        if _matches(combined, keywords):
            tags.append(f"affiliation:{affiliation}")
            added_affiliations.add(affiliation)
    if (
        source_affiliation
        and source_affiliation not in added_affiliations
        and source_affiliation in VALID_TAGS["affiliation"]
    ):
        tags.append(f"affiliation:{source_affiliation}")

    # 5. Format (zero or more)
    format_keywords = {
        "team": ["team"],
        "in-hand": ["in hand", "in-hand"],
        "clinic": ["clinic", "clinics"],
        "workshop": ["workshop", "workshops"],
    }
    for fmt, keywords in format_keywords.items():
        if _matches(combined, keywords):
            tags.append(f"format:{fmt}")

    # 6. Scope (at most one; geographic). International before national, and
    # 'national' requires a qualifying phrase so "National Trust" doesn't match.
    if _matches(combined, ["international", "cic", "ccio"]):
        tags.append("scope:international")
    elif _matches(combined, [
        "national championship", "national championships",
        "national final", "national finals", "national series",
        "national event", "national events", "area final", "area finals",
    ]):
        tags.append("scope:national")

    # 7. Age group (zero or more). 'senior' must not be "senior citizen(s)".
    if re.search(r"\bseniors?\b(?!\s+citizens?)", combined):
        tags.append("age:senior")
    if _matches(combined, ["junior", "u21", "under 21"]):
        tags.append("age:junior")
    if _matches(combined, ["young rider", "young riders"]):
        tags.append("age:young-rider")
    if _matches(combined, ["adult"]):
        tags.append("age:adult")

    # 8. Special (zero or more)
    if _matches(combined, ["qualifier", "area qualifier"]):
        tags.append("special:qualifier")
    if _matches(combined, ["invitational", "by invitation"]):
        tags.append("special:invitational")
    mm = _matches(combined, ["mountain and moorland", "m and m"])
    nb = _matches(combined, ["native breed", "native breeds", "native pony", "native ponies"])
    if mm:
        tags.append("special:mountain-and-moorland")
    if nb:
        tags.append("special:native-breed")
    if not (mm or nb) and _matches(combined, ["breed"]):
        tags.append("special:breed-specific")
    if _matches(combined, ["100km", "160km", "long format", "multi-day", "multi day"]):
        tags.append("special:long-format")

    # 9. Named series (zero or more) — precision-gated from series_seeds.json:
    # a distinctive keyword must match AND any require/exclude rules must pass
    # (e.g. "Sunshine Tour" only with "qualifier" and not "csi").
    for key, rule in _name_series_rules().items():
        if not _matches(combined, [k.lower() for k in rule.get("keywords", [])]):
            continue
        require = rule.get("require_keywords")
        if require and not _matches(combined, [k.lower() for k in require]):
            continue
        exclude = rule.get("exclude_keywords")
        if exclude and _matches(combined, [k.lower() for k in exclude]):
            continue
        tags.append(f"series:{key}")

    # 10. BS class series (zero or more). Junior/Senior take precedence over the
    # bare "foxhunter" class, whose keyword their names also contain.
    matched_classes = [
        key
        for key, rule in _class_series_rules().items()
        if _matches(combined, [k.lower() for k in rule.get("keywords", [])])
    ]
    if {"junior-foxhunter", "senior-foxhunter"} & set(matched_classes):
        matched_classes = [c for c in matched_classes if c != "foxhunter"]
    for key in matched_classes:
        tags.append(f"class:{key}")

    # Drop anything not in the vocabulary (defensive; drift is caught by tests).
    return [tag for tag in tags if validate_tag(tag)]


# Human-readable overrides for values that don't title-case cleanly.
_DISPLAY_OVERRIDES = {
    "british-dressage": "British Dressage",
    "british-showjumping": "British Showjumping",
    "british-eventing": "British Eventing",
    "british-horseball": "British Horseball",
    "pony-club": "Pony Club",
    "endurance-gb": "Endurance GB",
    "hpa-polo": "HPA Polo",
    "bsps": "BSPS",
    "bsha": "BSHA",
    "nsea": "NSEA",
    "bs-club": "BS Club",
    "blue-chip": "Blue Chip",
    "just-for-schools": "Just for Schools",
    "sunshine-tour-uk": "Sunshine Tour (UK)",
    "british-novice": "British Novice",
    "junior-foxhunter": "Junior Foxhunter",
    "senior-foxhunter": "Senior Foxhunter",
}


def get_tag_display_name(tag: str) -> str:
    """Convert a tag to a human-readable label.

    Examples: "discipline:dressage" -> "Dressage";
    "affiliation:bsps" -> "BSPS"; "affiliation:endurance-gb" -> "Endurance GB".
    """
    if ":" not in tag:
        return tag
    _, value = tag.split(":", 1)
    if value in _DISPLAY_OVERRIDES:
        return _DISPLAY_OVERRIDES[value]
    return value.replace("-", " ").title()


def filter_by_tag(competitions: list, tag: str) -> list:
    """Filter competitions by a specific tag."""
    return [c for c in competitions if tag in deserialize_tags(c.tags)]


def get_all_tags_by_category(competitions: list, category: str) -> set[str]:
    """Get all unique tags in a category from a list of competitions."""
    tags = set()
    for c in competitions:
        for tag in deserialize_tags(c.tags):
            if tag.startswith(f"{category}:"):
                tags.add(tag)
    return tags
