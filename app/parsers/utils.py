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

# ── Event type keyword patterns ──────────────────────────────────────
# Loaded from tag_keywords in venue_seeds.json on demand.
# Returns (keyword, event_type) pairs, e.g. ("clinic", "training").
_EVENT_TYPE_PATTERNS_CACHED: list[tuple[str, str]] | None = None

# Map from tag_keywords key → DB event_type value
_TAG_TO_EVENT_TYPE = {
    "type:training": "training",
    "type:venue-hire": "venue_hire",
    "type:show": "show",
    "type:social": "social",
    "type:other": "other",
}


def _load_event_type_patterns() -> list[tuple[str, str]]:
    """Load event type keywords from tag_keywords in seed data.

    Returns list of (keyword, event_type) tuples sorted by specificity
    (longer keywords first to match more specific patterns).
    """
    global _EVENT_TYPE_PATTERNS_CACHED
    if _EVENT_TYPE_PATTERNS_CACHED is not None:
        return _EVENT_TYPE_PATTERNS_CACHED

    patterns: list[tuple[str, str]] = []

    try:
        from app.seed_data import get_tag_keywords

        tag_kw = get_tag_keywords()
        for tag_key, keywords in tag_kw.items():
            event_type = _TAG_TO_EVENT_TYPE.get(tag_key)
            if not event_type:
                continue
            for kw in keywords:
                patterns.append((kw.lower(), event_type))

    except Exception:
        # Fallback
        patterns = [
            ("arena hire", "venue_hire"),
            ("school hire", "venue_hire"),
            ("course hire", "venue_hire"),
            ("hire", "venue_hire"),
            ("training", "training"),
            ("clinic", "training"),
            ("workshop", "training"),
        ]

    # Sort by length (longest first) to match more specific patterns first
    patterns.sort(key=lambda x: -len(x[0]))

    _EVENT_TYPE_PATTERNS_CACHED = patterns
    return patterns


def _get_event_type_patterns() -> list[tuple[str, str]]:
    """Get cached event type patterns (loads on first call)."""
    return _load_event_type_patterns()


# Backward compat aliases
def _get_non_competition_patterns() -> list[tuple[str, str]]:
    """Get event type patterns as (keyword, event_type) tuples.

    Backward-compatible wrapper — callers that used this for non-competition
    detection can now check event_type != "competition".
    """
    return _get_event_type_patterns()


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


# ── Competition discipline patterns ──────────────────────────────────
# Regex patterns for inferring the competition discipline from event
# name/description text.  Loaded from seed data via _load_discipline_patterns().
# Kept as hardcoded fallback for backwards compatibility if seed data is unavailable.
_DISCIPLINE_PATTERNS_FALLBACK: list[tuple[str, re.Pattern]] = [
    ("Show Jumping", re.compile(r"show\s*jump|SJQ\b|SJ\b|BS\s", re.IGNORECASE)),
    ("Dressage", re.compile(r"dressage|BD\b", re.IGNORECASE)),
    ("Eventing", re.compile(r"eventing|one.day.event|ODE\b|horse\s*trial|ECQ\b", re.IGNORECASE)),
    ("Cross Country", re.compile(r"cross\s*country|XC\b|show.?cross", re.IGNORECASE)),
    ("Arena Eventing", re.compile(r"arena\s*eventing", re.IGNORECASE)),
    ("Combined Training", re.compile(r"combined\s*training|\bCT\b", re.IGNORECASE)),
    ("Hunter Trial", re.compile(r"hunter\s*trial", re.IGNORECASE)),
    ("Working Hunter", re.compile(r"working\s*hunter|WHP\b", re.IGNORECASE)),
    ("Showing", re.compile(r"\bshowing\b", re.IGNORECASE)),
    ("Tetrathlon", re.compile(r"tetrathlon|triathlon|\btet\b", re.IGNORECASE)),
    ("Endurance", re.compile(r"endurance|pleasure\s*ride", re.IGNORECASE)),
    ("Mounted Games", re.compile(r"mounted\s*games", re.IGNORECASE)),
    ("Gymkhana", re.compile(r"gymkhana", re.IGNORECASE)),
    ("Polocrosse", re.compile(r"polocrosse", re.IGNORECASE)),
    ("Polo", re.compile(r"\bpolo\b", re.IGNORECASE)),
    ("Driving", re.compile(r"carriage\s*driv|driving\s*trial", re.IGNORECASE)),
    ("Drag Hunt", re.compile(r"draghound|drag\s*hunt", re.IGNORECASE)),
    ("Hobby Horse", re.compile(r"hobby\s*horse", re.IGNORECASE)),
    ("Horse Boarding", re.compile(r"horse\s*boarding", re.IGNORECASE)),
]

# Lazy-loaded patterns from seed data
_DISCIPLINE_PATTERNS_LOADED = None


def _load_discipline_patterns() -> list[tuple[str, re.Pattern]]:
    """Load and compile discipline patterns from seed data.

    All disciplines in seed data are competition disciplines by definition
    (non-competition types like Training/Venue Hire are in tag_keywords).
    Falls back to hardcoded patterns if seed data is unavailable.
    """
    try:
        from app.seed_data import get_discipline_seeds
        seeds = get_discipline_seeds()
        patterns = []
        for discipline, data in seeds.items():
            aliases = data.get("aliases", [])
            if aliases:
                # Build regex: "\balias1\b|\balias2\b" with word boundaries
                pattern_parts = [r'\b' + re.escape(a) + r'\b' for a in aliases]
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


_TRAINING_FALSE_POSITIVES = re.compile(
    r"combined\s+training|arena\s+eventing\s+training",
    re.IGNORECASE,
)


def _detect_event_type(name_lower: str) -> str:
    """Detect event type from name keywords.

    Returns one of: "competition", "training", "venue_hire", "show".
    Checks venue_hire and show first (most specific),
    then training, defaulting to competition.

    Guards against false positives like "Combined Training" (a discipline,
    not event_type=training).
    """
    for keyword, event_type in _get_event_type_patterns():
        if keyword in name_lower:
            # Guard: "training" inside "combined training" is a discipline name
            if keyword == "training" and _TRAINING_FALSE_POSITIVES.search(name_lower):
                continue
            return event_type
    return "competition"


def classify_event(name: str, description: str = "") -> tuple[str | None, str]:
    """Classify an event by examining its name and optional description.

    Determines discipline and event_type INDEPENDENTLY:
    - "Dressage Training" → ("Dressage", "training")
    - "Arena Hire" → (None, "venue_hire")
    - "Spring Show Jumping Championship" → ("Show Jumping", "competition")

    Returns (discipline, event_type) where:
    - discipline: canonical discipline name or None
    - event_type: "competition" | "training" | "venue_hire" | "show"
    """
    combined = f"{name} {description}".lower()
    name_lower = name.lower()

    # Step 1: Detect event_type from name keywords
    event_type = _detect_event_type(name_lower)

    # Step 2: Try to match a competition discipline from name + description
    discipline = None
    for disc, pattern in get_discipline_patterns():
        if pattern.search(combined):
            discipline = disc
            break

    return discipline, event_type


def infer_discipline(text: str) -> str | None:
    """Infer the equestrian discipline from event name/description text.

    Returns the first matching discipline, or None.
    """
    discipline, _ = classify_event(text)
    return discipline


def is_competition_event(name: str) -> bool:
    """Return True if the event name looks like a competition.

    Deprecated: prefer classify_event() which returns (discipline, event_type).
    Kept for backward compatibility.
    """
    _, event_type = classify_event(name)
    return event_type == "competition"


def should_skip_event(discipline: str | None, name: str) -> bool:
    """Return True if an event would be classified as non-competition.

    Deprecated: parsers should no longer skip events.  Instead, capture
    all events and let classify_event() / the scanner determine
    event_type.  Kept for backward compatibility during migration.
    """
    if discipline:
        canonical = normalise_discipline(discipline)
        if not canonical:
            return True
    _, event_type = classify_event(name)
    return event_type != "competition"


# ── Discipline normalisation ──────────────────────────────────────────
# Maps lowercase raw discipline → canonical value.
# All entries here are competition disciplines. Training/Venue Hire are
# event types, not disciplines — they're handled by _detect_event_type().
_DISCIPLINE_CANONICAL: dict[str, str] = {
    # Show Jumping
    "showjumping": "Show Jumping",
    "show jumping": "Show Jumping",
    "british showjumping": "Show Jumping",
    "affiliated showjumping": "Show Jumping",
    "affiliated show jumping": "Show Jumping",
    "unaffiliated showjumping": "Show Jumping",
    "unaffiliated show jumping": "Show Jumping",
    "equitation jumping": "Show Jumping",
    "sj": "Show Jumping",
    # Dressage
    "dressage": "Dressage",
    "british dressage": "Dressage",
    "affiliated dressage": "Dressage",
    "unaffiliated dressage": "Dressage",
    # Eventing
    "eventing": "Eventing",
    "affiliated eventing": "Eventing",
    "unaffiliated eventing": "Eventing",
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
    # Arena Eventing
    "arena eventing": "Arena Eventing",
    # Showing
    "showing": "Showing",
    "shows": "Showing",
    "bsps": "Showing",
    # Working Hunter
    "working hunter": "Working Hunter",
    "working hunter pony": "Working Hunter",
    "whp": "Working Hunter",
    # Hunter Trial
    "hunter trial": "Hunter Trial",
    "hunter trials": "Hunter Trial",
    # Tetrathlon (includes winter triathlon)
    "tetrathlon": "Tetrathlon",
    "triathlon": "Tetrathlon",
    "tet": "Tetrathlon",
    # Endurance
    "endurance": "Endurance",
    "pleasure ride": "Endurance",
    "fun ride": "Endurance",
    # Gymkhana
    "gymkhana": "Gymkhana",
    "mounted games": "Mounted Games",
    # Drag Hunt
    "drag hunt": "Drag Hunt",
    "draghunt": "Drag Hunt",
    "draghound": "Drag Hunt",
    "draghounds": "Drag Hunt",
    "drag hunting": "Drag Hunt",
    # Polo / Polocrosse
    "polo": "Polo",
    "polocrosse": "Polocrosse",
    # Other
    "driving": "Driving",
    "carriage driving": "Driving",
    "working equitation": "Working Hunter",
    "hobby horse": "Hobby Horse",
    # Horse Boarding
    "horse boarding": "Horse Boarding",
}


def normalise_discipline(raw: str | None) -> str | None:
    """Normalise a raw discipline string to a canonical discipline name.

    Returns the canonical discipline name, or None if not recognised.
    Only maps to competition disciplines — Training/Venue Hire are event
    types handled separately by _detect_event_type().

    Handles composite strings like "Showing, Other" or
    "Showjumping, Hunter Trial/Cross Country" by splitting on , and /
    and returning the first canonical match.
    """
    if not raw:
        return None

    raw_stripped = raw.strip()

    # Try direct match first (most common case)
    result = _try_normalise_single(raw_stripped.lower())
    if result:
        return result

    # Handle composite discipline strings: split on "," and "/"
    parts = re.split(r"[,/]", raw_stripped)
    for part in parts:
        part = part.strip()
        if part:
            result = _try_normalise_single(part.lower())
            if result:
                return result

    # No mapping found — return None so classifier can infer from name
    return None


def _try_normalise_single(raw_lower: str) -> str | None:
    """Try to normalise a single discipline string (lowercase).

    Handles underscore-separated API codes (e.g. "show_jumping" → "show jumping")
    so parsers can pass raw source values without pre-mapping.
    """
    # Normalise underscores to spaces (e.g. Equipe API "show_jumping")
    normalised = raw_lower.replace("_", " ")

    # Try seed data first
    try:
        from app.seed_data import get_discipline_seeds
        seeds = get_discipline_seeds()
        for canonical, data in seeds.items():
            aliases_lower = [a.lower() for a in data.get("aliases", [])]
            if normalised in aliases_lower or raw_lower in aliases_lower:
                return canonical
    except (ImportError, Exception):
        pass

    # Fall back to hardcoded mappings
    return _DISCIPLINE_CANONICAL.get(normalised) or _DISCIPLINE_CANONICAL.get(raw_lower)


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
