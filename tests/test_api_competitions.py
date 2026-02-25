"""Tests for the /api/competitions endpoints.

Uses an in-memory SQLite database and FastAPI TestClient.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.models import Competition, Source, Venue

# In-memory async engine for tests — StaticPool shares one connection across threads
TEST_ENGINE = create_async_engine(
    "sqlite+aiosqlite://",
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = async_sessionmaker(TEST_ENGINE, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables before each test, drop after."""
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _override_get_session():
    async with TestSession() as session:
        yield session


def _get_app():
    """Build a minimal FastAPI app with just the competitions router."""
    from fastapi import FastAPI

    from app.routers.competitions import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = _override_get_session
    return app


async def _seed(count: int = 3) -> list[int]:
    """Seed the database with a source, venues, and competitions. Returns competition IDs."""
    async with TestSession() as session:
        src = Source(
            name="Test Source",
            url="https://example.com",
            parser_key="test",
            enabled=True,
            created_at=datetime.utcnow(),
        )
        session.add(src)
        await session.flush()

        # Create venues
        venues = []
        for i in range(count):
            venue = Venue(
                name=f"Venue {i + 1}",
                postcode="TE1 2ST" if i == 0 else None,
            )
            session.add(venue)
            await session.flush()
            venues.append(venue)

        ids = []
        for i in range(count):
            comp = Competition(
                source_id=src.id,
                name=f"Test Competition {i + 1}",
                date_start=date(2026, 3, 15 + i),
                venue_id=venues[i].id,
                discipline="Show Jumping" if i % 2 == 0 else "Dressage",
                has_pony_classes=i == 0,
                event_type="competition",
                url=f"https://example.com/comp/{i + 1}",
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
            )
            session.add(comp)
            await session.flush()
            ids.append(comp.id)
        await session.commit()
    return ids


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------
class TestListCompetitions:
    @pytest.mark.asyncio
    async def test_list_returns_all(self):
        app = _get_app()
        await _seed(3)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/competitions")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_list_ordered_by_date(self):
        app = _get_app()
        await _seed(3)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/competitions")

        data = resp.json()
        dates = [d["date_start"] for d in data]
        assert dates == sorted(dates)

    @pytest.mark.asyncio
    async def test_filter_by_date_from(self):
        app = _get_app()
        await _seed(3)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/competitions?date_from=2026-03-17")

        data = resp.json()
        assert len(data) == 1
        assert data[0]["date_start"] == "2026-03-17"

    @pytest.mark.asyncio
    async def test_filter_by_date_to(self):
        app = _get_app()
        await _seed(3)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/competitions?date_to=2026-03-15")

        data = resp.json()
        assert len(data) == 1
        assert data[0]["date_start"] == "2026-03-15"

    @pytest.mark.asyncio
    async def test_filter_pony_only(self):
        app = _get_app()
        await _seed(3)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/competitions?pony_only=true")

        data = resp.json()
        assert len(data) == 1
        assert data[0]["has_pony_classes"] is True

    @pytest.mark.asyncio
    async def test_empty_list(self):
        app = _get_app()
        # No seeding

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/competitions")

        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Single competition endpoint
# ---------------------------------------------------------------------------
class TestGetCompetition:
    @pytest.mark.asyncio
    async def test_get_by_id(self):
        app = _get_app()
        ids = await _seed(1)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/competitions/{ids[0]}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Competition 1"
        assert data["discipline"] == "Show Jumping"

    @pytest.mark.asyncio
    async def test_not_found(self):
        app = _get_app()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/competitions/9999")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# iCalendar export endpoint
# ---------------------------------------------------------------------------
class TestICalExport:
    @pytest.mark.asyncio
    async def test_ical_returns_calendar(self):
        app = _get_app()
        ids = await _seed(1)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/competitions/{ids[0]}/ical")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/calendar; charset=utf-8"
        body = resp.text
        assert "BEGIN:VCALENDAR" in body
        assert "BEGIN:VEVENT" in body
        assert "END:VEVENT" in body
        assert "END:VCALENDAR" in body

    @pytest.mark.asyncio
    async def test_ical_contains_event_data(self):
        app = _get_app()
        ids = await _seed(1)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/competitions/{ids[0]}/ical")

        body = resp.text
        assert "SUMMARY:Test Competition 1" in body
        assert "DTSTART;VALUE=DATE:20260315" in body
        # Single-day event: DTEND is next day (exclusive)
        assert "DTEND;VALUE=DATE:20260316" in body
        assert "LOCATION:Venue 1\\, TE1 2ST" in body

    @pytest.mark.asyncio
    async def test_ical_content_disposition(self):
        app = _get_app()
        ids = await _seed(1)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/competitions/{ids[0]}/ical")

        assert "attachment" in resp.headers.get("content-disposition", "")
        assert ".ics" in resp.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_ical_not_found(self):
        app = _get_app()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/competitions/9999/ical")

        assert resp.status_code == 404
