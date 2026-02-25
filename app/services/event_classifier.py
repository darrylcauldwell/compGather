"""Event classification service - single source of truth for is_competition determination."""

from typing import Optional

from app.parsers.utils import (
    _get_non_competition_patterns,
    get_discipline_patterns,
    normalise_discipline,
)


class EventClassifier:
    """Single source of truth for event classification.

    Centralized classification logic replacing scattered classify_event() and
    normalise_discipline() calls throughout the codebase. Provides deterministic,
    testable classification with a clear strategy.

    Classification Strategy:
    1. Check event name for non-competition keywords (Training, Venue Hire) — highest priority
    2. Normalise parser-provided discipline hint if given
    3. Check name + description for competition discipline keywords
    4. Default to (None, True) if no matches — assume it's a competition

    Returns (canonical_discipline, is_competition) where:
    - Non-competition: ("Training", False) or ("Venue Hire", False)
    - Competition: ("Show Jumping", True) or (None, True) for unknown disciplines
    """

    @staticmethod
    def classify(
        name: str,
        discipline_hint: Optional[str] = None,
        description: str = "",
    ) -> tuple[Optional[str], bool]:
        """Classify an event by name, discipline hint, and description.

        Args:
            name: Event name/title (required)
            discipline_hint: Parser-provided discipline text (optional, e.g., "Show Jumping")
            description: Event description/details (optional)

        Returns:
            (canonical_discipline, is_competition) tuple
        """
        combined = f"{name} {description}".lower()
        name_lower = name.lower()

        # Step 1: Non-competition keywords in name take priority
        # These indicate training events, venue hire, etc.
        for keyword, non_comp_discipline in _get_non_competition_patterns():
            if keyword in name_lower:
                return (non_comp_discipline, False)

        # Step 2: Normalise parser-provided discipline hint
        # If parser gave us a discipline, use that classification
        if discipline_hint:
            canonical, is_comp = normalise_discipline(discipline_hint)
            if canonical:
                return (canonical, is_comp)

        # Step 3: Try to infer competition discipline from name + description
        # Look for patterns like "Show Jumping", "Eventing", "Dressage", etc.
        for discipline, pattern in get_discipline_patterns():
            if pattern.search(combined):
                return (discipline, True)

        # Step 4: No match — unknown discipline, assume it's a competition
        return (None, True)
