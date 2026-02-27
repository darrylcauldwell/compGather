from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


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
    url: str | None
    first_seen_at: datetime
    last_seen_at: datetime

    model_config = {"from_attributes": True}


# --- Scans ---
class ScanCreate(BaseModel):
    source_id: int | None = None


class ScanOut(BaseModel):
    id: int
    source_id: int | None
    started_at: datetime
    completed_at: datetime | None
    status: str
    competitions_found: int
    competitions_found_comp: int = 0
    competitions_found_training: int = 0
    error: str | None

    model_config = {"from_attributes": True}


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
    has_pony_classes: bool = False
    classes: list[str] = []
    url: str | None = None
    description: str | None = None


# Backward compatibility alias during migration
ExtractedCompetition = ExtractedEvent
