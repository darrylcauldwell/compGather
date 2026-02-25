from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    postcode: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    distance_miles: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Tracking columns for data quality management
    source: Mapped[str] = mapped_column(Text, default="dynamic")  # "seed_data" or "dynamic"
    seed_batch: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # e.g., "batch_1", "web_crawl_high_value"
    validation_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # e.g., "website", "postcode_api", "nominatim"
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 1.0 for validated, None for dynamic


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    parser_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scanned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    competitions: Mapped[List["Competition"]] = relationship(back_populates="source")
    scans: Mapped[List["Scan"]] = relationship(back_populates="source")


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("sources.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    date_start: Mapped[date] = mapped_column(Date, nullable=False)
    date_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    venue_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("venues.id"), nullable=True
    )
    discipline: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    has_pony_classes: Mapped[bool] = mapped_column(Boolean, default=False)
    event_type: Mapped[str] = mapped_column(Text, default="competition")  # "competition", "training", "venue_hire"
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of tag strings
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    venue_match_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_extract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    source: Mapped["Source"] = relationship(back_populates="competitions")
    venue: Mapped[Optional["Venue"]] = relationship()

    @property
    def is_competition(self) -> bool:
        """Backward-compatible derived property: True when event_type is 'competition'."""
        return self.event_type == "competition"

    @property
    def venue_name(self) -> str:
        return self.venue.name if self.venue else "Unknown"

    @property
    def venue_postcode(self) -> str | None:
        return self.venue.postcode if self.venue else None

    @property
    def latitude(self) -> float | None:
        return self.venue.latitude if self.venue else None

    @property
    def longitude(self) -> float | None:
        return self.venue.longitude if self.venue else None

    @property
    def distance_miles(self) -> float | None:
        return self.venue.distance_miles if self.venue else None


class VenueAlias(Base):
    __tablename__ = "venue_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alias: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    venue_id: Mapped[int] = mapped_column(Integer, ForeignKey("venues.id"), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    origin: Mapped[str] = mapped_column(Text, default="dynamic")  # "seed_data" or "dynamic"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DisciplineAlias(Base):
    __tablename__ = "discipline_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alias: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    discipline: Mapped[str] = mapped_column(Text, nullable=False)  # FK reference to canonical name
    source: Mapped[str] = mapped_column(Text, default="seed_data")  # "seed_data" or "dynamic"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class VenueMatchReview(Base):
    __tablename__ = "venue_match_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalised_name: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_venue_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("venues.id"), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    postcode: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parser_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    parser_lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="pending")
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("sources.id"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="pending")
    competitions_found: Mapped[int] = mapped_column(Integer, default=0)
    competitions_found_comp: Mapped[int] = mapped_column(Integer, default=0)
    competitions_found_training: Mapped[int] = mapped_column(Integer, default=0)
    venue_match_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    source: Mapped[Optional["Source"]] = relationship(back_populates="scans")
