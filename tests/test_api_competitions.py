"""Tests for the /api/competitions and /api/geocode endpoints.

Uses an in-memory SQLite database and FastAPI TestClient.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, patch

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
    """Build a minimal FastAPI app with the competitions and geocode routers."""
    from fastapi import FastAPI

    from app.routers.competitions import geocode_router, router

    app = FastAPI()
    app.include_router(router)
    app.include_router(geocode_router)
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
    async def test_ical_contains_valarm(self):
        app = _get_app()
        ids = await _seed(1)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/competitions/{ids[0]}/ical")

        body = resp.text
        assert "BEGIN:VALARM" in body
        assert "TRIGGER:-P7D" in body
        assert "ACTION:DISPLAY" in body
        assert "END:VALARM" in body

    @pytest.mark.asyncio
    async def test_ical_contains_description(self):
        app = _get_app()
        ids = await _seed(1)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/competitions/{ids[0]}/ical")

        body = resp.text
        assert "DESCRIPTION:" in body
        assert "Book: Test Competition 1" in body
        assert "Venue: Venue 1" in body

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


# ---------------------------------------------------------------------------
# Geocode endpoint
# ---------------------------------------------------------------------------
class TestGeocodeEndpoint:
    @pytest.mark.asyncio
    async def test_geocode_valid_postcode(self):
        app = _get_app()

        with patch(
            "app.routers.competitions.geocode_postcode",
            new_callable=AsyncMock,
            return_value=(51.5074, -0.1278),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/geocode?postcode=SW1A+1AA")

        assert resp.status_code == 200
        data = resp.json()
        assert data["postcode"] == "SW1A 1AA"
        assert data["lat"] == 51.5074
        assert data["lng"] == -0.1278

    @pytest.mark.asyncio
    async def test_geocode_invalid_postcode(self):
        app = _get_app()

        with patch(
            "app.routers.competitions.geocode_postcode",
            new_callable=AsyncMock,
            return_value=None,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/geocode?postcode=INVALID")

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_reverse_geocode(self):
        app = _get_app()

        with patch(
            "app.routers.competitions.reverse_geocode",
            new_callable=AsyncMock,
            return_value="SW1A 1AA",
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/geocode/reverse",
                    json={"lat": 51.5074, "lng": -0.1278},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["postcode"] == "SW1A 1AA"

    @pytest.mark.asyncio
    async def test_reverse_geocode_failure(self):
        app = _get_app()

        with patch(
            "app.routers.competitions.reverse_geocode",
            new_callable=AsyncMock,
            return_value=None,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/geocode/reverse",
                    json={"lat": 0.0, "lng": 0.0},
                )

        assert resp.status_code == 400
