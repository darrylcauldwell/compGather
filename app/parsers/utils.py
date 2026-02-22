"""Shared utilities for parser modules.

Common patterns used across multiple parsers: postcode extraction,
pony-class detection, past-event filtering, and JSON-LD parsing.
"""

from __future__ import annotations

import json
import re
from datetime import date

from bs4 import BeautifulSoup

# UK postcode regex — matches formats like "SW1A 1AA", "M1 1AA", "B33 8TH"
# Requires a space between outward and inward codes to avoid false positives
POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s+\d[A-Z]{2}\b", re.IGNORECASE)

# Keywords that indicate pony/junior classes
PONY_KEYWORDS = [
    "pony", "ponies", "junior", "u18", "under 18",
    "u16", "under 16", "u14", "under 14",
    "trailblazer", "nsea",
]

# Keywords for non-competition events (clinics, training, etc.)
NON_COMPETITION_KEYWORDS = [
    "clinic", "workshop", "seminar", "lecture", "course",
    "masterclass", "demonstration", "lesson", "tuition",
    "arena hire", "school hire", " hire",
]


def is_future_event(date_start: str, date_end: str | None = None) -> bool:
    """Return True if the event hasn't ended yet.

    For multi-day events, checks date_end; for single-day, checks date_start.
    Returns True if the date can't be parsed (benefit of the doubt).
    """
    today = date.today()
    check_date = date_end or date_start
    try:
        return date.fromisoformat(check_date) >= today
    except (ValueError, TypeError):
        return True


def extract_postcode(text: str) -> str | None:
    """Extract the first UK postcode from text, or None."""
    match = POSTCODE_RE.search(text)
    return match.group(0).strip() if match else None


def detect_pony_classes(text: str) -> bool:
    """Return True if text contains any pony/junior keywords."""
    lower = text.lower()
    return any(kw in lower for kw in PONY_KEYWORDS)


def is_competition_event(name: str) -> bool:
    """Return True if the event name looks like a competition (not a clinic/lesson)."""
    lower = name.lower()
    return not any(kw in lower for kw in NON_COMPETITION_KEYWORDS)


# Discipline keywords for inferring type from event name/description
_DISCIPLINE_PATTERNS = [
    ("Show Jumping", re.compile(r"show\s*jump|SJ\b|BS\s", re.IGNORECASE)),
    ("Dressage", re.compile(r"dressage|BD\b", re.IGNORECASE)),
    ("Eventing", re.compile(r"eventing|one.day.event|ODE\b|horse\s*trial|BE\b", re.IGNORECASE)),
    ("Cross Country", re.compile(r"cross\s*country|XC\b|show.?cross|arena\s*eventing", re.IGNORECASE)),
    ("Combined Training", re.compile(r"combined\s*training|CT\b", re.IGNORECASE)),
    ("Hunter Trial", re.compile(r"hunter\s*trial", re.IGNORECASE)),
    ("Showing", re.compile(r"\bshowing\b|working\s*hunter", re.IGNORECASE)),
    ("Endurance", re.compile(r"endurance|pleasure\s*ride", re.IGNORECASE)),
    ("Gymkhana", re.compile(r"gymkhana|mounted\s*games", re.IGNORECASE)),
    ("Polo", re.compile(r"\bpolo\b|polocrosse", re.IGNORECASE)),
    ("Driving", re.compile(r"carriage\s*driv|driving\s*trial", re.IGNORECASE)),
]


def infer_discipline(text: str) -> str | None:
    """Infer the equestrian discipline from event name/description text.

    Returns the first matching discipline, or None if unclear.
    """
    for discipline, pattern in _DISCIPLINE_PATTERNS:
        if pattern.search(text):
            return discipline
    return None


# ── Discipline normalisation ──────────────────────────────────────────
# Maps lowercase raw discipline → canonical value.
_DISCIPLINE_CANONICAL: dict[str, str] = {
    # Show Jumping
    "showjumping": "Show Jumping",
    "show jumping": "Show Jumping",
    "british showjumping": "Show Jumping",
    "unaffiliated showjumping": "Show Jumping",
    "unaffiliated show jumping": "Show Jumping",
    "equitation jumping": "Show Jumping",
    "sj": "Show Jumping",
    # Dressage
    "dressage": "Dressage",
    "british dressage": "Dressage",
    "unaffiliated dressage": "Dressage",
    # Eventing
    "eventing": "Eventing",
    "one day event": "Eventing",
    "eventer trial": "Eventing",
    "express eventing": "Eventing",
    "eventers challenge": "Eventing",
    "horse trial": "Eventing",
    "horse trials": "Eventing",
    # Cross Country
    "cross country": "Cross Country",
    "xc": "Cross Country",
    "show cross": "Cross Country",
    "showcross": "Cross Country",
    # Combined Training
    "combined training": "Combined Training",
    "ct": "Combined Training",
    # Showing
    "showing": "Showing",
    "shows": "Showing",
    "bsps": "Showing",
    "working hunter": "Showing",
    # Hunter Trial
    "hunter trial": "Hunter Trial",
    "hunter trials": "Hunter Trial",
    # Pony Club
    "pony club": "Pony Club",
    # NSEA
    "nsea": "NSEA",
    # Agricultural Show
    "agricultural show": "Agricultural Show",
    # Endurance
    "endurance": "Endurance",
    "pleasure ride": "Endurance",
    "fun ride": "Endurance",
    # Gymkhana
    "gymkhana": "Gymkhana",
    "mounted games": "Gymkhana",
    # Other
    "polo": "Other",
    "polocrosse": "Other",
    "driving": "Other",
    "carriage driving": "Other",
    "working equitation": "Other",
    "hobby horse": "Other",
    "demonstrations": "Other",
    "demonstration": "Other",
    "social": "Other",
    "vip event": "Other",
    "riding club": "Other",
    "mixed events": "Other",
    "other": "Other",
    # Non-competition: Venue Hire
    "arena hire": "Venue Hire",
    "arena/course hire": "Venue Hire",
    "arena/coursehire": "Venue Hire",
    "xc course hire": "Venue Hire",
    "arena/school hire": "Venue Hire",
    "arena booking": "Venue Hire",
    "arena eventing": "Venue Hire",
    "course hire": "Venue Hire",
    "school hire": "Venue Hire",
    # Non-competition: Training
    "tuition/lessons": "Training",
    "tuition": "Training",
    "lessons": "Training",
    "training clinics": "Training",
    "training clinic": "Training",
    "schooling": "Training",
    "clinic": "Training",
    "clinics": "Training",
    "camps": "Training",
    "camp": "Training",
    "training": "Training",
}

_NON_COMPETITION_DISCIPLINES = {"Venue Hire", "Training"}


def normalise_discipline(raw: str | None) -> tuple[str | None, bool]:
    """Normalise a raw discipline string to a canonical value.

    Returns (canonical_discipline, is_competition).
    Non-competition categories (Venue Hire, Training) get is_competition=False.
    """
    if not raw:
        return raw, True

    canonical = _DISCIPLINE_CANONICAL.get(raw.strip().lower())
    if canonical:
        return canonical, canonical not in _NON_COMPETITION_DISCIPLINES

    # No mapping found — return as-is, assume it's a competition
    return raw.strip(), True


# Regex to strip BS-style show numbering: "(1)", "(2) - SPONSORED BY DUBARRY", etc.
_SHOW_NUMBER_RE = re.compile(r"\s*\(\d+\)(\s*-\s*.+)?$")

# Regex to strip trailing parenthetical event descriptions: "(Festival)", "(Small Pony Premier)", etc.
# Only matches parens containing known event keywords — preserves location qualifiers like "(Cumbria)"
_TRAILING_EVENT_PAREN_RE = re.compile(
    r"\s*\([^)]*(?:Premier|Festival|Championship|Finals|Qualifier|Scope|Senior|Junior|Pony|Winter|Summer|League)[^)]*\)\s*$",
    re.IGNORECASE,
)

# Regex to strip "Limited" suffix (various forms)
_LIMITED_RE = re.compile(r"\s+Limited$", re.IGNORECASE)

# Regex to strip trailing abbreviation codes: "- Chspc", "- Vwh", etc.
# Max 5 chars to avoid stripping location names like "Munstead", "Guernsey"
_TRAILING_ABBREV_RE = re.compile(r"\s*-\s+[A-Z][A-Za-z]{1,4}$")

# Common suffixes to normalise (order matters — longest first)
_VENUE_SUFFIXES = [
    " riding & competition centre",
    " competition & training centre",
    " competition and training centre",
    " equestrian competition centre",
    " equestrian complex ltd",
    " equestrian centre ltd",
    " equestrian club ltd",
    " equestrian village",
    " equestrian centre",
    " equestrian center",
    " equestrian complex",
    " equestrian club",
    " equestrian ltd",
    " equestrian",
    " international arena",
    " competition centre",
    " training centre",
    " riding centre",
    " riding center",
    " riding school",
    " ltd",
    " ec",
]

# Known venue spelling corrections (applied after suffix stripping)
_VENUE_ALIASES = {
    "Southview": "South View",
    "Pickering Grange Farm": "Pickering Grange",
}


def normalise_venue_name(name: str) -> str:
    """Normalise a venue name to a canonical form.

    - Title-cases the name
    - Strips BS show numbering like "(1)", "(2) - SPONSORED BY..."
    - Normalises common suffixes (e.g. "Equestrian" → "Equestrian Centre")
    - Trims whitespace
    """
    if not name:
        return name

    # Strip show numbering: "(1)", "(2) - SPONSORED BY..."
    cleaned = _SHOW_NUMBER_RE.sub("", name)

    # Strip trailing event descriptions in parentheses: "(Festival)", "(Small Pony Premier)"
    cleaned = _TRAILING_EVENT_PAREN_RE.sub("", cleaned)

    # Title-case (handles "ELAND LODGE" → "Eland Lodge")
    cleaned = cleaned.strip().title()

    # Strip "Limited" suffix
    cleaned = _LIMITED_RE.sub("", cleaned)

    # Strip trailing abbreviation codes: "- Chspc", "- EC" (before suffix matching)
    cleaned = _TRAILING_ABBREV_RE.sub("", cleaned)

    # Normalise suffixes: strip common venue type endings
    lower = cleaned.lower()
    for suffix in _VENUE_SUFFIXES:
        if lower.endswith(suffix):
            cleaned = cleaned[: len(cleaned) - len(suffix)].rstrip()
            break

    # Collapse multiple spaces
    cleaned = re.sub(r"\s{2,}", " ", cleaned)

    # Strip trailing punctuation (dashes, colons, ampersands)
    cleaned = cleaned.strip().rstrip("-–—:&").strip()

    # Apply known venue aliases
    if cleaned in _VENUE_ALIASES:
        cleaned = _VENUE_ALIASES[cleaned]

    return cleaned


def extract_json_ld_event(soup: BeautifulSoup) -> dict | None:
    """Extract the first Event-typed JSON-LD block from a page.

    Handles: single objects, arrays, and Yoast @graph wrappers.
    """
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            continue

        if isinstance(data, dict):
            if data.get("@type") == "Event":
                return data
            # Yoast / schema.org @graph wrapper
            for item in data.get("@graph", []):
                if isinstance(item, dict) and item.get("@type") == "Event":
                    return item
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("@type") == "Event":
                    return item

    return None
