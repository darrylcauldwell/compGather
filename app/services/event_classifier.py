"""Event classification service - single source of truth for discipline + event_type."""

import re
from typing import Optional

from app.parsers.utils import (
    _detect_event_type,
    get_discipline_patterns,
    normalise_discipline,
)

# Signals that an event is spectator-worthy (drives the app's "Watch" tab):
# international competition codes, a FEI star rating, or marquee-show wording.
_INTL_CODE = re.compile(r"\b(?:CSIO?|CDIO?|CCIO?|CHIO?)\b", re.IGNORECASE)
_STAR = re.compile(r"\d\s*\*")
_SPECTATOR_TERMS = re.compile(
    r"\b(?:county show|country fair|agricultural|national championship|"
    r"world championship|european championship|world cup|nations cup|"
    r"international horse show)\b",
    re.IGNORECASE,
)


def classify_spectator(name: str, event_type: str) -> bool:
    """Whether an event belongs on the 'Watch' tab (worth spectating).

    Used for scraped events; curated static shows set this explicitly. An event
    can be both enterable (event_type == 'competition') and spectator-worthy.
    """
    if event_type == "show":
        return True
    text = name or ""
    return bool(_INTL_CODE.search(text) or _STAR.search(text) or _SPECTATOR_TERMS.search(text))


class EventClassifier:
    """Single source of truth for event classification.

    Determines discipline and event_type INDEPENDENTLY:
    - Discipline is detected from parser hint or name+description keywords
    - Event type is detected from name keywords (training, venue hire, etc.)

    This allows correct tagging like "Dressage Training" →
    discipline="Dressage", event_type="training".

    Returns (discipline, event_type) where:
    - discipline: canonical name ("Show Jumping", "Dressage", etc.) or None
    - event_type: "competition" | "training" | "venue_hire" | "show"
    """

    @staticmethod
    def classify(
        name: str,
        discipline_hint: Optional[str] = None,
        description: str = "",
        event_type_hint: Optional[str] = None,
    ) -> tuple[Optional[str], str]:
        """Classify an event by name, discipline hint, and description.

        Args:
            name: Event name/title (required)
            discipline_hint: Parser-provided discipline text (optional)
            description: Event description/details (optional)
            event_type_hint: Parser-provided event type (optional, e.g. "show")

        Returns:
            (canonical_discipline, event_type) tuple
        """
        combined = f"{name} {description}".lower()
        name_lower = name.lower()

        # Step 1: Detect event_type from name keywords, or use parser hint
        if event_type_hint:
            event_type = event_type_hint
        else:
            event_type = _detect_event_type(name_lower)

        # Step 2: Normalise parser-provided discipline hint
        discipline = None
        if discipline_hint:
            discipline = normalise_discipline(discipline_hint)

        # Step 3: If no discipline from hint, try to infer from name + description
        if not discipline:
            for disc, pattern in get_discipline_patterns():
                if pattern.search(combined):
                    discipline = disc
                    break

        return (discipline, event_type)
