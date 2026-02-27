"""Scanner integration tests — require running database and services.

These tests verify the scan pipeline logic using mocked external services.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import Competition, Source, Venue
from app.schemas import ExtractedCompetition


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_scan_creates_competitions(db_session):
    """Test that _scan_source creates competition records from extracted data."""
    source = Source(name="Test Source", url="https://example.com", enabled=True)
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    mock_extracted = [
        ExtractedCompetition(
            name="Summer Show",
            date_start="2026-07-15",
            venue_name="Test Arena",
            venue_postcode="SW1A 1AA",
            classes=["Pony 1.00m", "Open 1.10m"],
        )
    ]

    # Mock the parser returned by get_parser
    mock_parser = MagicMock()
    mock_parser.fetch_and_parse = AsyncMock(return_value=mock_extracted)

    with (
        patch("app.services.scanner.get_parser", return_value=mock_parser),
        patch("app.services.scanner.geocode_postcode", new_callable=AsyncMock, return_value=(51.5, -0.1)),
    ):
        from app.services.scanner import _scan_source

        count, match_counts, scan_comp_count, scan_training_count = await _scan_source(db_session, source)

    assert count == 1
    assert match_counts.get("new", 0) == 1
    assert scan_comp_count == 1
    assert scan_training_count == 0

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    result = await db_session.execute(
        select(Competition).options(selectinload(Competition.venue))
    )
    comps = result.scalars().all()
    assert len(comps) == 1
    assert comps[0].name == "Summer Show"
    assert comps[0].venue_id is not None
    assert comps[0].venue_match_type == "new"
    assert comps[0].date_start == date(2026, 7, 15)

    # Verify venue was created correctly
    venue_result = await db_session.execute(
        select(Venue).where(Venue.name == "Test Arena")
    )
    venue = venue_result.scalar_one_or_none()
    assert venue is not None
    assert venue.latitude == 51.5
    assert venue.longitude == -0.1
    assert venue.postcode == "SW1A 1AA"
