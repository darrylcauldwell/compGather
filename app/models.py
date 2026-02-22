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
    venue_name: Mapped[str] = mapped_column(Text, nullable=False)
    venue_postcode: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    distance_miles: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    discipline: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    has_pony_classes: Mapped[bool] = mapped_column(Boolean, default=False)
    is_competition: Mapped[bool] = mapped_column(Boolean, default=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_extract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    source: Mapped["Source"] = relationship(back_populates="competitions")


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
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    source: Mapped[Optional["Source"]] = relationship(back_populates="scans")
