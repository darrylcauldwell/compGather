"""Shared utilities for parser modules.

Common patterns used across multiple parsers: postcode extraction,
pony-class detection, past-event filtering, event classification,
and JSON-LD parsing.
"""

from __future__ import annotations

import json
import re
from datetime import date

from bs4 import BeautifulSoup

from app.seed_data import get_ambiguous_names

# UK postcode regex — matches formats like "SW1A 1AA", "M1 1AA", "B33 8TH"
# Requires a space between outward and inward codes to avoid false positives
POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s+\d[A-Z]{2}\b", re.IGNORECASE)

# Keywords that indicate pony/junior classes
PONY_KEYWORDS = [
    "pony", "ponies", "junior", "u18", "under 18",
    "u16", "under 16", "u14", "under 14",
    "trailblazer", "nsea",
]

# ── Non-competition keyword patterns ─────────────────────────────────
# Load dynamically from seed_data.json (canonical source) on demand.
# Cached for performance.
_NON_COMPETITION_PATTERNS_CACHED = None


def _load_non_competition_patterns() -> list[tuple[str, str]]:
    """Load non-competition keywords from canonical seed_data.json source.

    Returns list of (keyword, discipline) tuples for all non-competition
    disciplines (Training, Venue Hire, etc.) sorted by specificity
    (longer keywords first to match more specific patterns).
    """
    global _NON_COMPETITION_PATTERNS_CACHED
    if _NON_COMPETITION_PATTERNS_CACHED is not None:
        return _NON_COMPETITION_PATTERNS_CACHED

    patterns: list[tuple[str, str]] = []

    try:
        from app.seed_data import get_discipline_seeds

        seeds = get_discipline_seeds()
        for discipline, data in seeds.items():
            # Only non-competition disciplines (is_competition=False or missing)
            if data.get("is_competition", False):
                continue

            # Add all aliases for this discipline
            for alias in data.get("aliases", []):
                patterns.append((alias.lower(), discipline))

    except Exception:
        # Fallback if seed data is unavailable (shouldn't happen in production)
        patterns = [
            ("arena hire", "Venue Hire"),
            ("school hire", "Venue Hire"),
            ("course hire", "Venue Hire"),
            (" hire", "Venue Hire"),
        ]

    # Sort by length (longest first) to match more specific patterns first
    patterns.sort(key=lambda x: -len(x[0]))

    _NON_COMPETITION_PATTERNS_CACHED = patterns
    return patterns


def _get_non_competition_patterns() -> list[tuple[str, str]]:
    """Get cached non-competition patterns (loads on first call)."""
    return _load_non_competition_patterns()


# Legacy list for any external consumers — now loaded from canonical source
NON_COMPETITION_KEYWORDS = None


def _get_non_competition_keywords() -> list[str]:
    """Get list of non-competition keywords from canonical source."""
    return [kw for kw, _ in _get_non_competition_patterns()]


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


# UK postcode with or without space — for normalisation
_POSTCODE_COMPACT_RE = re.compile(
    r"^([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\.?$", re.IGNORECASE
)


def normalise_postcode(postcode: str | None) -> str | None:
    """Normalise a UK postcode: uppercase, single space, strip trailing dots.

    Returns None if the value doesn't look like a valid UK postcode.
    """
    if not postcode or not postcode.strip():
        return None
    m = _POSTCODE_COMPACT_RE.match(postcode.strip())
    if not m:
        return None
    return f"{m.group(1).upper()} {m.group(2).upper()}"


_PC_RE = re.compile(r"\bPC\b")


def detect_pony_classes(text: str) -> bool:
    """Return True if text contains any pony/junior keywords or 'PC' (Pony Club)."""
    lower = text.lower()
    return any(kw in lower for kw in PONY_KEYWORDS) or bool(_PC_RE.search(text))


# ── Competition discipline patterns ──────────────────────────────────
# Regex patterns for inferring the competition discipline from event
# name/description text.  Loaded from seed data via _load_discipline_patterns().
# Kept as hardcoded fallback for backwards compatibility if seed data is unavailable.
_DISCIPLINE_PATTERNS_FALLBACK: list[tuple[str, re.Pattern]] = [
    ("Show Jumping", re.compile(r"show\s*jump|SJQ\b|SJ\b|BS\s", re.IGNORECASE)),
    ("Dressage", re.compile(r"dressage|BD\b", re.IGNORECASE)),
    ("Eventing", re.compile(r"eventing|one.day.event|ODE\b|horse\s*trial|BE\b|ECQ\b", re.IGNORECASE)),
    ("Cross Country", re.compile(r"cross\s*country|XC\b|show.?cross|arena\s*eventing", re.IGNORECASE)),
    ("Combined Training", re.compile(r"combined\s*training|CT\b", re.IGNORECASE)),
    ("Hunter Trial", re.compile(r"hunter\s*trial", re.IGNORECASE)),
    ("Showing", re.compile(r"\bshowing\b|working\s*hunter", re.IGNORECASE)),
    ("Endurance", re.compile(r"endurance|pleasure\s*ride", re.IGNORECASE)),
    ("Pony Club", re.compile(r"pony\s*club|\bPC\b", re.IGNORECASE)),
    ("Gymkhana", re.compile(r"gymkhana|mounted\s*games", re.IGNORECASE)),
    ("Polocrosse", re.compile(r"polocrosse", re.IGNORECASE)),
    ("Polo", re.compile(r"\bpolo\b", re.IGNORECASE)),
    ("Driving", re.compile(r"carriage\s*driv|driving\s*trial", re.IGNORECASE)),
    ("Drag Hunt", re.compile(r"draghound|drag\s*hunt", re.IGNORECASE)),
    ("Hobby Horse", re.compile(r"hobby\s*horse", re.IGNORECASE)),
]

# Lazy-loaded patterns from seed data
_DISCIPLINE_PATTERNS_LOADED = None


def _load_discipline_patterns() -> list[tuple[str, re.Pattern]]:
    """Load and compile discipline patterns from seed data.

    Falls back to hardcoded patterns if seed data is unavailable.
    """
    try:
        from app.seed_data import get_discipline_seeds
        seeds = get_discipline_seeds()
        patterns = []
        for discipline, data in seeds.items():
            if data.get("is_competition"):  # Only competition disciplines
                aliases = data.get("aliases", [])
                if aliases:
                    # Build regex: "alias1|alias2|alias3" with word boundaries
                    pattern_parts = [re.escape(a) for a in aliases]
                    pattern_str = "|".join(pattern_parts)
                    patterns.append((
                        discipline,
                        re.compile(pattern_str, re.IGNORECASE)
                    ))
        return patterns if patterns else _DISCIPLINE_PATTERNS_FALLBACK
    except (ImportError, Exception):
        # Fallback if seed data loading fails
        return _DISCIPLINE_PATTERNS_FALLBACK


def get_discipline_patterns() -> list[tuple[str, re.Pattern]]:
    """Get compiled discipline patterns with lazy loading."""
    global _DISCIPLINE_PATTERNS_LOADED
    if _DISCIPLINE_PATTERNS_LOADED is None:
        _DISCIPLINE_PATTERNS_LOADED = _load_discipline_patterns()
    return _DISCIPLINE_PATTERNS_LOADED


def classify_event(name: str, description: str = "") -> tuple[str | None, bool]:
    """Classify an event by examining its name and optional description.

    This is the single source of truth for event classification.  It
    determines both the discipline and whether the event is a competition.

    Returns (discipline, is_competition):
      - For training events: ("Training", False)
      - For venue hire:      ("Venue Hire", False)
      - For competitions:    (<discipline>, True)   — discipline may be None
    """
    combined = f"{name} {description}".lower()

    # Step 1: Check for non-competition keywords in the event name.
    # Only the event *name* is checked (not description) to avoid false
    # positives from descriptions that mention e.g. "clinic" incidentally.
    # Keywords are loaded from canonical seed_data.json (Training, Venue Hire, etc.)
    name_lower = name.lower()
    for keyword, non_comp_discipline in _get_non_competition_patterns():
        if keyword in name_lower:
            return non_comp_discipline, False

    # Step 2: Try to match a competition discipline from name + description.
    for discipline, pattern in get_discipline_patterns():
        if pattern.search(combined):
            return discipline, True

    # Step 3: No match — return None discipline, assume competition.
    return None, True


def infer_discipline(text: str) -> str | None:
    """Infer the equestrian discipline from event name/description text.

    Returns the first matching *competition* discipline, or None.
    For full classification (including Training/Venue Hire), use
    classify_event() instead.
    """
    discipline, _ = classify_event(text)
    return discipline


def is_competition_event(name: str) -> bool:
    """Return True if the event name looks like a competition.

    Deprecated: prefer classify_event() which returns (discipline, is_competition).
    Kept for backward compatibility with scanner.py and any external callers.
    """
    _, is_comp = classify_event(name)
    return is_comp


def should_skip_event(discipline: str | None, name: str) -> bool:
    """Return True if an event would be classified as non-competition.

    Deprecated: parsers should no longer skip events.  Instead, capture
    all events and let classify_event() / the scanner determine
    is_competition.  Kept for backward compatibility during migration.
    """
    if discipline:
        _, is_comp = normalise_discipline(discipline)
        if not is_comp:
            return True
    _, is_comp = classify_event(name)
    return not is_comp


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
    # Drag Hunt
    "drag hunt": "Drag Hunt",
    "draghunt": "Drag Hunt",
    "draghound": "Drag Hunt",
    "draghounds": "Drag Hunt",
    "drag hunting": "Drag Hunt",
    # Other
    "polo": "Other",
    "polocrosse": "Polocrosse",
    "driving": "Other",
    "carriage driving": "Other",
    "working equitation": "Other",
    "hobby horse": "Hobby Horse",
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
    "rally": "Training",
    "rallies": "Training",
    "polework": "Training",
    "pole work": "Training",
    "gridwork": "Training",
    "grid work": "Training",
    "flatwork": "Training",
    "flat work": "Training",
    # Non-competition: Other
    "box office": "Venue Hire",
    # Pony Club-specific non-competition types
    "test training": "Training",
    "safeguarding training": "Training",
    "cpd": "Training",
    "officials training": "Training",
    "team training": "Training",
    "area training": "Training",
    "coach and assessor training": "Training",
    "committee meeting": "Training",
    # Pony Club-specific competition types → canonical
    "area competition": "Pony Club",
    "area competition - teams": "Pony Club",
    "test": "Pony Club",
    "sundry": "Other",
}

_NON_COMPETITION_DISCIPLINES = {"Venue Hire", "Training"}


def normalise_discipline(raw: str | None) -> tuple[str | None, bool]:
    """Normalise a raw discipline string to a canonical value.

    Returns (canonical_discipline, is_competition).
    Non-competition categories (Venue Hire, Training) get is_competition=False.
    Checks seed data first, then falls back to hardcoded mappings.
    """
    if not raw:
        return raw, True

    raw_lower = raw.strip().lower()

    # Try seed data first
    try:
        from app.seed_data import get_discipline_seeds
        seeds = get_discipline_seeds()
        for canonical, data in seeds.items():
            if raw_lower in [a.lower() for a in data.get("aliases", [])]:
                is_comp = data.get("is_competition", True)
                return canonical, is_comp
    except (ImportError, Exception):
        pass

    # Fall back to hardcoded mappings
    canonical = _DISCIPLINE_CANONICAL.get(raw_lower)
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
# Suffix stripping is iterative, so combinations like "X Equestrian Centre Ltd"
# are handled across multiple passes without needing every combo listed.
_VENUE_SUFFIXES = [
    " riding & competition centre",
    " competition & training centre",
    " competition and training centre",
    " competition & livery centre",
    " competition & livery yard",
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
    " equine sports centre",
    " equine centre",
    " equine",
    " equitation centre",
    " equitation",
    " international arena",
    " competition centre",
    " training centre",
    " events centre",
    " event centre",
    " sports centre",
    " riding centre",
    " riding center",
    " riding school",
    " show centre",
    " indoor arena",
    " ltd",
    " ecc",
    " e c",
    " ec",
]

# Outward code regex for disambiguation: "GL7" from "GL7 7JW"
_OUTWARD_CODE_RE = re.compile(r"^([A-Z]{1,2}\d[A-Z\d]?)\s", re.IGNORECASE)


def disambiguate_venue(name: str, postcode: str | None) -> str:
    """Append outward postcode code to ambiguous venue names.

    "Rectory Farm" + "GL7 7JW" → "Rectory Farm (GL7)"
    Returns name unchanged if not ambiguous or no postcode available.
    """
    if name not in get_ambiguous_names() or not postcode:
        return name
    m = _OUTWARD_CODE_RE.match(postcode.strip().upper())
    if m:
        return f"{name} ({m.group(1)})"
    return name


# Regex to extract venue from "... at Venue Name" in event names
_AT_VENUE_RE = re.compile(r"\bat\s+(.+?)$", re.IGNORECASE)


def extract_venue_from_name(name: str) -> str | None:
    """Try to extract a venue name from an event name containing 'at VenueName'.

    E.g. "Berks and Bucks Draghounds - Draghound Meet at Stowell Park"
    → "Stowell Park"

    Returns None if no 'at ...' pattern found.
    """
    m = _AT_VENUE_RE.search(name)
    if m:
        venue = m.group(1).strip()
        # Skip if it looks like a date or is too short
        if len(venue) > 2 and not re.match(r"\d", venue):
            return venue
    return None


def normalise_venue_name(name: str) -> str:
    """Normalise a venue name to a canonical form.

    - Title-cases the name
    - Strips BS show numbering like "(1)", "(2) - SPONSORED BY..."
    - Normalises common suffixes (e.g. "Equestrian" → "Equestrian Centre")
    - Trims whitespace
    """
    if not name or not name.strip():
        return "Tbc"

    # Online/virtual venues → canonical "Online"
    if name.strip().lower().startswith("online") or name.strip().lower() == "virtual":
        return "Online"

    # Strip show numbering: "(1)", "(2) - SPONSORED BY..."
    cleaned = _SHOW_NUMBER_RE.sub("", name)

    # Strip trailing event descriptions in parentheses: "(Festival)", "(Small Pony Premier)"
    cleaned = _TRAILING_EVENT_PAREN_RE.sub("", cleaned)

    # Title-case (handles "ELAND LODGE" → "Eland Lodge")
    cleaned = cleaned.strip().title()

    # Fix outward code in disambiguation suffix: title() lowercases "GL7" to "Gl7"
    # Restore to uppercase: "Rectory Farm (Gl7)" → "Rectory Farm (GL7)"
    cleaned = re.sub(
        r"\(([A-Za-z]{1,2}\d[A-Za-z\d]?)\)$",
        lambda m: "(" + m.group(1).upper() + ")",
        cleaned,
    )

    # Strip embedded postcodes: "Lodge Farm TN12 7ET" → "Lodge Farm",
    # "(B48 7ER)" → "", "Cf71 7Rq" (name is just a postcode) → left alone
    cleaned_no_pc = re.sub(r"\s*\(?" + POSTCODE_RE.pattern + r"\)?\s*", " ", cleaned, flags=re.IGNORECASE).strip()
    if cleaned_no_pc:
        cleaned = cleaned_no_pc

    # Strip "Limited" suffix
    cleaned = _LIMITED_RE.sub("", cleaned)

    # Strip trailing abbreviation codes: "- Chspc", "- EC" (before suffix matching)
    cleaned = _TRAILING_ABBREV_RE.sub("", cleaned)

    # Normalise suffixes: strip common venue type endings (iterative —
    # handles combos like "X Equestrian Centre Ltd" across passes)
    while True:
        lower = cleaned.lower()
        matched = False
        for suffix in _VENUE_SUFFIXES:
            if lower.endswith(suffix):
                cleaned = cleaned[: len(cleaned) - len(suffix)].rstrip()
                matched = True
                break
        if not matched:
            break

    # Collapse multiple spaces
    cleaned = re.sub(r"\s{2,}", " ", cleaned)

    # Strip trailing punctuation and whitespace (dashes, colons, ampersands, commas, periods)
    cleaned = re.sub(r"[-–—:&,.\s]+$", "", cleaned).strip()

    # Strip orphaned trailing prepositions left after suffix removal
    cleaned = re.sub(r"\s+(?:Of|At|In|For|The|And|&)\s*$", "", cleaned, flags=re.IGNORECASE).strip()

    # Junk data guards: reject postcodes, plus codes, empty/short strings
    if not cleaned or len(cleaned) < 2:
        return "Tbc"
    if re.match(r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$", cleaned, re.IGNORECASE):
        return "Tbc"
    if re.match(r"^[A-Z0-9]{4,}\+[A-Z0-9]+", cleaned, re.IGNORECASE):
        return "Tbc"

    # Reject URLs
    if re.match(r"^https?://", cleaned, re.IGNORECASE):
        return "Tbc"

    # Reject very long names (job adverts, descriptions) — likely junk
    if len(cleaned) > 100:
        return "Tbc"

    # Address truncation: strip trailing address parts after commas.
    # "Ardenrun Showground, Tandridge Lane, Lingfield" → "Ardenrun Showground"
    # Preserves short qualified names like "Higher Farm, Cheshire" (1 comma, <40 chars).
    if "," in cleaned:
        parts = [p.strip() for p in cleaned.split(",")]
        first_part = parts[0]
        if len(first_part) >= 4:
            # 2+ commas → almost certainly an address, keep first part
            # 1 comma + long → address ("Berkshire College Of Agriculture, Maidenhead")
            # 1 comma + short → qualifier ("Higher Farm, Cheshire") — keep as-is
            if len(parts) > 2 or len(cleaned) > 50:
                cleaned = first_part

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
