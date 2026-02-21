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
POSTCODE_RE = re.compile(r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}", re.IGNORECASE)

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
    "arena hire", "school hire",
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
]


def infer_discipline(text: str) -> str | None:
    """Infer the equestrian discipline from event name/description text.

    Returns the first matching discipline, or None if unclear.
    """
    for discipline, pattern in _DISCIPLINE_PATTERNS:
        if pattern.search(text):
            return discipline
    return None


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
