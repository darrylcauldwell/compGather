"""Tag management for event classification."""

import json
from typing import Optional

# Canonical tag vocabulary
VALID_TAGS = {
    # Discipline (required in extract_tags, but only one allowed)
    "discipline": [
        "show-jumping", "dressage", "eventing", "cross-country",
        "combined-training", "hunter-trial", "showing", "endurance",
        "pony-club", "nsea", "agricultural-show", "gymkhana",
        "polocrosse", "polo", "driving", "drag-hunt", "hobby-horse", "other"
    ],
    # Event Type (required in extract_tags, but only one allowed)
    "type": ["competition", "training", "venue-hire"],
    # Pony Eligibility (optional, at most one)
    "pony": ["only", "open"],
    # Level (optional, at most one)
    "level": ["beginner", "novice", "intermediate", "advanced", "championship", "mixed"],
    # Affiliation (optional, zero or more)
    "affiliation": [
        "british-dressage", "british-showjumping", "british-eventing",
        "pony-club", "nsea", "endurance-gb", "unaffiliated", "bsps", "bsha"
    ],
    # Format (optional, zero or more)
    "format": ["individual", "team", "in-hand", "clinic", "workshop"],
    # Scope (optional, at most one)
    "scope": ["local", "regional", "national", "international", "championship"],
    # Age Group (optional, zero or more)
    "age": ["junior", "young-rider", "adult", "senior"],
    # Special (optional, zero or more)
    "special": [
        "qualifier", "invitational", "breed-specific", "working-hunter",
        "long-format", "mountain-and-moorland", "native-breed"
    ]
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
    # Validate all tags before serializing
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


def extract_tags(
    name: str,
    description: str = "",
    discipline: Optional[str] = None,
    is_competition: bool = True,  # kept for backward compat; unused internally
) -> list[str]:
    """Extract tags from event name/description based on keywords.

    This function extracts BOTH discipline and event type INDEPENDENTLY from the
    event name/description, allowing for granular tagging like "Dressage Training"
    (discipline:dressage + type:training) instead of forcing an either/or choice.

    Args:
        name: Event name
        description: Event description
        discipline: Canonical discipline (from classify_event, used as fallback only)
        is_competition: Deprecated — type is now extracted independently from keywords

    Returns:
        List of valid tags to attach to the event
    """
    tags: list[str] = []
    combined = f"{name} {description}".lower()

    # 1. Extract DISCIPLINE independently from event name/description
    # This is separate from the pre-classified discipline, allowing us to detect
    # the actual discipline even if the event was classified as "Training"
    discipline_keywords = {
        "show-jumping": ["show jump", "sjq", "sj ", "bs "],
        "dressage": ["dressage", "bd "],
        "eventing": ["eventing", "one day event", "ode ", "horse trial", "be ", "ecq"],
        "cross-country": ["cross country", "xc ", "show cross"],
        "combined-training": ["combined training", "ct "],
        "hunter-trial": ["hunter trial"],
        "showing": ["showing", "working hunter"],
        "endurance": ["endurance", "pleasure ride", "fun ride"],
        "pony-club": ["pony club", "pc "],
        "nsea": ["nsea"],
        "agricultural-show": ["agricultural show"],
        "gymkhana": ["gymkhana", "mounted games"],
        "polocrosse": ["polocrosse"],
        "polo": [" polo", "polo "],
        "driving": ["carriage driving", "driving trial"],
        "drag-hunt": ["drag hunt", "draghound"],
        "hobby-horse": ["hobby horse"],
        "arena-eventing": ["arena eventing"],
    }

    extracted_discipline = None
    for disc_tag, keywords in discipline_keywords.items():
        if any(kw in combined for kw in keywords):
            extracted_discipline = disc_tag
            break

    # Use extracted discipline, fall back to pre-classified if needed
    final_discipline = extracted_discipline or (
        {
            "Show Jumping": "show-jumping",
            "Dressage": "dressage",
            "Eventing": "eventing",
            "Cross Country": "cross-country",
            "Combined Training": "combined-training",
            "Hunter Trial": "hunter-trial",
            "Showing": "showing",
            "Endurance": "endurance",
            "Pony Club": "pony-club",
            "NSEA": "nsea",
            "Agricultural Show": "agricultural-show",
            "Gymkhana": "gymkhana",
            "Polocrosse": "polocrosse",
            "Polo": "polo",
            "Driving": "driving",
            "Drag Hunt": "drag-hunt",
            "Hobby Horse": "hobby-horse",
            "Arena Eventing": "arena-eventing",
        }.get(discipline, "other") if discipline else None
    )

    if final_discipline:
        tags.append(f"discipline:{final_discipline}")

    # 2. Extract EVENT TYPE independently from event name/description
    # Check for venue hire first (most specific)
    if any(kw in combined for kw in ["hire", "arena hire", "course hire", "school hire", "arena booking"]):
        tags.append("type:venue-hire")
    # Check for training keywords
    elif any(kw in combined for kw in ["training", "clinic", "workshop", "seminar", "lecture", "masterclass", "demonstration", "lesson", "tuition", "coaching", "rally", "grid work", "gridwork", "flatwork", "flat work", "schooling", "polework", "pole work", "course walk"]):
        tags.append("type:training")
    # Default to competition
    else:
        tags.append("type:competition")

    # 3. Pony eligibility (optional)
    if "pony club" in combined or "trailblazer" in combined or "pc " in combined:
        tags.append("pony:only")
    elif any(kw in combined for kw in ["open to", "all ages", "all classes", "all levels"]):
        tags.append("pony:open")
    # else: no pony tag = unknown

    # 4. Level (optional, only if explicitly stated)
    level_keywords = {
        "beginner": ["beginner"],
        "novice": ["novice"],
        "intermediate": ["intermediate"],
        "advanced": ["advanced", "advanced level"],
        "championship": ["championship", "grand prix", "national championship"],
        "mixed": ["all levels", "mixed level"],
    }
    for level, keywords in level_keywords.items():
        if any(kw in combined for kw in keywords):
            tags.append(f"level:{level}")
            break

    # 5. Affiliation (optional, zero or more)
    affiliation_keywords = {
        "british-dressage": ["british dressage", "bd "],
        "british-showjumping": ["british showjumping", "bs area"],
        "british-eventing": ["british eventing", "be "],
        "pony-club": ["pony club"],
        "nsea": ["nsea"],
        "endurance-gb": ["endurance gb"],
        "bsps": ["bsps", "british show pony"],
        "bsha": ["bsha", "british show horse"],
    }
    for affiliation, keywords in affiliation_keywords.items():
        if any(kw in combined for kw in keywords):
            tags.append(f"affiliation:{affiliation}")

    # 6. Format (optional, zero or more)
    format_keywords = {
        "team": ["team", "team event"],
        "in-hand": ["in hand", "in-hand"],
        "clinic": ["clinic", "clinics"],
        "workshop": ["workshop", "workshops"],
    }
    for fmt, keywords in format_keywords.items():
        if any(kw in combined for kw in keywords):
            tags.append(f"format:{fmt}")

    # 7. Scope (optional, at most one - only obvious ones)
    scope_keywords = {
        "championship": ["championship", "national final", "area final"],
        "national": ["national", "national event"],
        "international": ["international", "cic", "ccio"],
    }
    for scope, keywords in scope_keywords.items():
        if any(kw in combined for kw in keywords):
            tags.append(f"scope:{scope}")
            break

    # 8. Age Group (optional, zero or more)
    age_keywords = {
        "junior": ["junior", "u21", "under 21"],
        "young-rider": ["young rider"],
        "senior": ["senior"],
        "adult": ["adult"],
    }
    for age, keywords in age_keywords.items():
        if any(kw in combined for kw in keywords):
            tags.append(f"age:{age}")

    # 9. Special (optional, zero or more)
    special_keywords = {
        "qualifier": ["qualifier", "area qualifier"],
        "invitational": ["invitational", "by invitation"],
        "breed-specific": ["breed", "mountain and moorland", "native breed"],
        "working-hunter": ["working hunter"],
        "long-format": ["endurance", "100km"],
    }
    for special, keywords in special_keywords.items():
        if any(kw in combined for kw in keywords):
            tags.append(f"special:{special}")

    # Validate all extracted tags
    validated_tags = [tag for tag in tags if validate_tag(tag)]

    return validated_tags


def get_tag_display_name(tag: str) -> str:
    """Convert tag to human-readable format.

    Examples:
        "discipline:dressage" → "Dressage"
        "level:intermediate" → "Intermediate"
        "affiliation:british-dressage" → "British Dressage"
    """
    if ":" not in tag:
        return tag

    category, value = tag.split(":", 1)

    # Title case with special handling
    display = value.replace("-", " ").title()

    # Capitalize acronyms
    display = display.replace("Bd", "BD").replace("Bs", "BS")
    display = display.replace("Bsps", "BSPS").replace("Bsha", "BSHA")
    display = display.replace("Nsea", "NSEA")

    return display


def filter_by_tag(competitions: list, tag: str) -> list:
    """Filter competitions by a specific tag."""
    return [
        c for c in competitions
        if tag in deserialize_tags(c.tags)
    ]


def get_all_tags_by_category(competitions: list, category: str) -> set[str]:
    """Get all unique tags in a category from a list of competitions.

    Example:
        get_all_tags_by_category(comps, "level") → {"level:novice", "level:advanced"}
    """
    tags = set()
    for c in competitions:
        for tag in deserialize_tags(c.tags):
            if tag.startswith(f"{category}:"):
                tags.add(tag)
    return tags
