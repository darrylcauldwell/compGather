"""Tag management for event classification."""

import json
from typing import Optional

# Canonical tag vocabulary
VALID_TAGS = {
    # Discipline (required in extract_tags, one or more allowed)
    "discipline": [
        "show-jumping", "dressage", "eventing", "cross-country",
        "combined-training", "hunter-trial", "arena-eventing",
        "showing", "working-hunter", "tetrathlon", "endurance", "gymkhana", "mounted-games",
        "polocrosse", "polo", "driving", "drag-hunt", "hobby-horse", "horse-boarding"
    ],
    # Event Type (required in extract_tags, but only one allowed)
    "type": ["competition", "training", "venue-hire", "show", "social", "other"],
    # Level (optional, at most one)
    "level": ["beginner", "novice", "intermediate", "advanced", "championship", "mixed"],
    # Affiliation (optional, zero or more)
    "affiliation": [
        "british-dressage", "british-showjumping", "british-eventing",
        "pony-club", "nsea", "endurance-gb", "unaffiliated",
        "bsps", "bsha", "british-horseball", "hpa-polo"
    ],
    # Format (optional, zero or more)
    "format": ["individual", "team", "in-hand", "clinic", "workshop"],
    # Scope (optional, at most one)
    "scope": ["local", "regional", "national", "international", "championship"],
    # Age Group (optional, zero or more)
    "age": ["junior", "young-rider", "adult", "senior"],
    # Special (optional, zero or more)
    "special": [
        "qualifier", "invitational", "breed-specific",
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


# Map from DB event_type values to tag type values
_EVENT_TYPE_TO_TAG = {
    "competition": "competition",
    "training": "training",
    "venue_hire": "venue-hire",
    "show": "show",
    "social": "social",
    "other": "other",
}


def extract_tags(
    name: str,
    description: str = "",
    discipline: Optional[str] = None,
    event_type: str = "competition",
    source_affiliation: Optional[str] = None,
) -> list[str]:
    """Extract tags from event name/description based on keywords.

    Extracts BOTH discipline(s) and event type INDEPENDENTLY, allowing
    granular tagging like "Dressage Training" → discipline:dressage + type:training.

    Args:
        name: Event name
        description: Event description
        discipline: Canonical discipline (from classifier, used as fallback)
        event_type: Event type from classifier ("competition"|"training"|"venue_hire"|"show")
        source_affiliation: Source-level affiliation tag (e.g. "british-dressage")

    Returns:
        List of valid tags to attach to the event
    """
    tags: list[str] = []
    combined = f"{name} {description}".lower()

    # 1. Extract DISCIPLINE(s) independently from event name/description
    # Collect ALL matching disciplines (no break on first match)
    discipline_keywords = {
        "show-jumping": ["show jump", "sjq", "sj ", "bs "],
        "dressage": ["dressage", "bd "],
        "eventing": ["eventing", "one day event", "ode ", "horse trial", "ecq"],
        "cross-country": ["cross country", "xc ", "show cross"],
        "arena-eventing": ["arena eventing"],
        "combined-training": ["combined training", " ct "],
        "hunter-trial": ["hunter trial"],
        "working-hunter": ["working hunter", "whp"],
        "showing": ["showing"],
        "tetrathlon": ["tetrathlon", "triathlon", " tet "],
        "endurance": ["endurance", "pleasure ride", "fun ride"],
        "gymkhana": ["gymkhana"],
        "mounted-games": ["mounted games"],
        "polocrosse": ["polocrosse"],
        "polo": [" polo", "polo "],
        "driving": ["carriage driving", "driving trial"],
        "drag-hunt": ["drag hunt", "draghound"],
        "hobby-horse": ["hobby horse"],
        "horse-boarding": ["horse boarding"],
    }

    extracted_disciplines: list[str] = []
    for disc_tag, keywords in discipline_keywords.items():
        if any(kw in combined for kw in keywords):
            extracted_disciplines.append(disc_tag)

    # Use extracted disciplines, fall back to pre-classified if none found
    if not extracted_disciplines and discipline:
        canonical_to_tag = {
            "Show Jumping": "show-jumping",
            "Dressage": "dressage",
            "Eventing": "eventing",
            "Cross Country": "cross-country",
            "Arena Eventing": "arena-eventing",
            "Combined Training": "combined-training",
            "Hunter Trial": "hunter-trial",
            "Showing": "showing",
            "Working Hunter": "working-hunter",
            "Tetrathlon": "tetrathlon",
            "Endurance": "endurance",
            "Gymkhana": "gymkhana",
            "Mounted Games": "mounted-games",
            "Polocrosse": "polocrosse",
            "Polo": "polo",
            "Driving": "driving",
            "Drag Hunt": "drag-hunt",
            "Hobby Horse": "hobby-horse",
            "Horse Boarding": "horse-boarding",
        }
        fallback = canonical_to_tag.get(discipline)
        if fallback:
            extracted_disciplines = [fallback]

    for disc_tag in extracted_disciplines:
        tags.append(f"discipline:{disc_tag}")

    # 2. Event type — use classifier result, mapped to tag format
    type_tag = _EVENT_TYPE_TO_TAG.get(event_type, "competition")
    tags.append(f"type:{type_tag}")

    # 3. Level (optional, only if explicitly stated)
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
        "british-eventing": ["british eventing"],
        "pony-club": ["pony club"],
        "nsea": ["nsea"],
        "endurance-gb": ["endurance gb"],
        "bsps": ["bsps", "british show pony"],
        "bsha": ["bsha", "british show horse"],
        "british-horseball": ["british horseball"],
        "hpa-polo": ["hpa polo", "hpa-polo"],
    }
    added_affiliations = set()
    for affiliation, keywords in affiliation_keywords.items():
        if any(kw in combined for kw in keywords):
            tags.append(f"affiliation:{affiliation}")
            added_affiliations.add(affiliation)

    # Add source-level affiliation if not already added from keywords
    if source_affiliation and source_affiliation not in added_affiliations:
        if source_affiliation in VALID_TAGS["affiliation"]:
            tags.append(f"affiliation:{source_affiliation}")

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
    display = display.replace("Hpa", "HPA")

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
