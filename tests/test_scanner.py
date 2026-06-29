"""Scanner integration tests — require running database and services.

These tests verify the scan pipeline logic using mocked external services.
"""

import logging
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import Competition, Scan, Source, Venue
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


@pytest_asyncio.fixture
async def scan_env():
    """In-memory DB with the scanner's global session factory patched to it."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    with patch("app.services.scanner.async_session", factory):
        yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_failed_scan_completes_without_crashing(scan_env):
    """Regression for the MissingGreenlet crash: the post-scan metrics block read
    scan.source.name, which lazy-loads after rollback in async context and raised,
    aborting run_scan (and all failed-scan metrics). It must now complete cleanly
    using plain locals, persisting the failed status."""
    from app.services.scanner import run_scan

    async with scan_env() as s:
        src = Source(name="Breaky", url="https://x.example", enabled=True, parser_key="generic")
        s.add(src)
        await s.commit()
        await s.refresh(src)
        sid = src.id

    mock_parser = MagicMock()
    mock_parser.fetch_and_parse = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("app.services.scanner.get_parser", return_value=mock_parser):
        await run_scan(sid)  # must NOT raise (previously raised MissingGreenlet)

    async with scan_env() as s:
        scan = (await s.execute(select(Scan).where(Scan.source_id == sid))).scalar_one()
        assert scan.status == "failed"
        assert "boom" in (scan.error or "")


@pytest.mark.asyncio
async def test_consecutive_zero_extract_streak(scan_env):
    from app.services.scanner import _consecutive_zero_extract_streak

    async with scan_env() as s:
        src = Source(name="Zeroes", url="https://z.example", enabled=True)
        s.add(src)
        await s.commit()
        await s.refresh(src)
        sid = src.id
        # Oldest -> newest: 5 found, then three zero-extract scans.
        for comp in (5, 0, 0, 0):
            s.add(Scan(
                source_id=sid, status="completed",
                started_at=datetime(2026, 1, 1), completed_at=datetime(2026, 1, 1),
                competitions_found=0, competitions_found_comp=comp,
                competitions_found_training=0,
            ))
        await s.commit()

        streak = await _consecutive_zero_extract_streak(s, sid)
    assert streak == 3


@pytest.mark.asyncio
async def test_threshold_warns_on_extracted_drop(scan_env, caplog):
    """A parser that silently stops returning events is now detected — the old
    new-insert comparison could not catch this once a source was seeded."""
    from app.services import scanner

    async with scan_env() as s:
        src = Source(name="Dropper", url="https://d.example", enabled=True)
        s.add(src)
        await s.commit()
        await s.refresh(src)
        sid = src.id
        prev = Scan(
            source_id=sid, status="completed",
            started_at=datetime(2026, 1, 1), completed_at=datetime(2026, 1, 1),
            competitions_found=0, competitions_found_comp=50, competitions_found_training=0,
        )
        cur = Scan(
            source_id=sid, status="completed",
            started_at=datetime(2026, 1, 2), completed_at=datetime(2026, 1, 2),
            competitions_found=0, competitions_found_comp=0, competitions_found_training=0,
        )
        s.add_all([prev, cur])
        await s.commit()
        await s.refresh(cur)

        with caplog.at_level(logging.WARNING, logger="app.services.scanner"):
            await scanner._check_scan_threshold(s, sid, cur, "Dropper", 0)

    assert any("Dropper" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_scheduler_rotates_past_failing_source():
    """A failing source must not monopolise the rolling queue: the scheduling
    cursor advances on every attempt, so the next tick picks a different source.
    Without the fix, an unscanned/failing source stays first forever."""
    from app.services import scheduler

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add_all([
            Source(name="AAA", url="https://a.example", enabled=True),
            Source(name="BBB", url="https://b.example", enabled=True),
        ])
        await s.commit()

    picked: list[int] = []

    async def fake_run_scan(source_id, scan_id=None):
        # Simulate a scan that does NOT succeed (so it never sets last_scanned_at
        # itself) — the scheduler's attempt-time stamp is what must rotate it out.
        picked.append(source_id)

    with patch("app.services.scheduler.async_session", factory), \
         patch("app.services.scheduler.run_scan", fake_run_scan):
        await scheduler._run_next_scan()
        await scheduler._run_next_scan()

    await engine.dispose()
    assert len(picked) == 2
    assert picked[0] != picked[1]  # rotated to the other source, not stuck on the first


@pytest.mark.asyncio
async def test_long_span_events_are_hidden(db_session):
    """Programme/league/badge-scheme entries (implausibly long span) are hidden;
    normal events and legitimate multi-week tours stay visible."""
    source = Source(name="Test Source", url="https://example.com", enabled=True)
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    mock_extracted = [
        ExtractedCompetition(  # 5-year "Badges" programme → hidden
            name="Faversham Badges Programme",
            date_start="2026-01-01", date_end="2030-12-31",
            venue_name="Faversham RC", venue_postcode="ME13 8XZ",
        ),
        ExtractedCompetition(  # ordinary one-day show → visible
            name="Normal One-Day Show",
            date_start="2026-07-15", date_end="2026-07-15",
            venue_name="Faversham RC", venue_postcode="ME13 8XZ",
        ),
        ExtractedCompetition(  # 48-day tour → legitimate, visible
            name="Multi-week Tour",
            date_start="2026-02-02", date_end="2026-03-22",
            venue_name="Faversham RC", venue_postcode="ME13 8XZ",
        ),
    ]
    mock_parser = MagicMock()
    mock_parser.fetch_and_parse = AsyncMock(return_value=mock_extracted)

    with (
        patch("app.services.scanner.get_parser", return_value=mock_parser),
        patch("app.services.scanner.geocode_postcode", new_callable=AsyncMock, return_value=(51.3, 0.9)),
    ):
        from app.services.scanner import _scan_source
        await _scan_source(db_session, source)

    result = await db_session.execute(select(Competition))
    by_name = {c.name: c for c in result.scalars().all()}
    assert by_name["Faversham Badges Programme"].hidden is True
    assert by_name["Normal One-Day Show"].hidden is False
    assert by_name["Multi-week Tour"].hidden is False
