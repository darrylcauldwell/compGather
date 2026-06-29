from __future__ import annotations

import json
from datetime import date, datetime

from pydantic import BaseModel, field_validator


# --- Sources ---
class SourceCreate(BaseModel):
    name: str
    url: str
    parser_key: str | None = None


class SourceUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    parser_key: str | None = None
    enabled: bool | None = None


class SourceOut(BaseModel):
    id: int
    name: str
    url: str
    parser_key: str | None
    enabled: bool
    last_scanned_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Competitions ---
class CompetitionOut(BaseModel):
    id: int
    source_id: int
    name: str
    date_start: date
    date_end: date | None
    venue_name: str
    venue_postcode: str | None
    discipline: str | None
    latitude: float | None
    longitude: float | None
    distance_miles: float | None
    event_type: str = "competition"
    tags: list[str] = []
    url: str | None
    first_seen_at: datetime
    last_seen_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("tags", mode="before")
    @classmethod
    def _deserialize_tags(cls, value: object) -> list[str]:
        """Competition.tags is stored as a JSON string; expose it as a list."""
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return value or []


# --- Extractor ---
class ExtractedEvent(BaseModel):
    """Raw event data extracted from a source.

    This schema is purely extractive - no classification happens here.
    Classification (competition vs training vs venue hire) is determined
    later by EventClassifier in scanner after all data is extracted.

    Fields represent raw data as extracted from the source; discipline is
    an optional hint from the parser, not a canonical value. The scanner
    will normalize discipline via EventClassifier.classify().
    """
    name: str
    date_start: str
    date_end: str | None = None
    venue_name: str
    venue_postcode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    discipline: str | None = None  # Raw discipline hint, not normalized
    event_type: str | None = None  # Raw event type hint (e.g. "show")
    has_pony_classes: bool = False
    classes: list[str] = []
    url: str | None = None
    description: str | None = None


# Backward compatibility alias during migration
ExtractedCompetition = ExtractedEvent
