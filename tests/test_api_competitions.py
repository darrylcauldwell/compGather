"""Tests for the /api/competitions and /api/geocode endpoints.

Uses an in-memory SQLite database and FastAPI TestClient.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
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
    async def test_filter_by_venue_id(self):
        app = _get_app()
        await _seed(3)
        # Resolve a real venue id (the map → Compete hand-off filters by it).
        from sqlalchemy import select

        async with TestSession() as session:
            venue_ids = (
                await session.execute(select(Venue.id).order_by(Venue.id))
            ).scalars().all()
        target = venue_ids[1]

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/competitions?venue_id={target}")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["venue_name"] == "Venue 2"

    @pytest.mark.asyncio
    async def test_filter_by_unknown_venue_id_empty(self):
        app = _get_app()
        await _seed(3)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/competitions?venue_id=999999")

        assert resp.status_code == 200
        assert resp.json() == []

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


# ---------------------------------------------------------------------------
# tags field + event_type filter (for the iOS app)
# ---------------------------------------------------------------------------
async def _seed_typed():
    """One competition (with tags) and one show, sharing a venue."""
    async with TestSession() as session:
        src = Source(name="S", url="https://e.example", parser_key="t", enabled=True,
                     created_at=datetime.utcnow())
        session.add(src)
        await session.flush()
        venue = Venue(name="V", postcode="TE1 2ST")
        session.add(venue)
        await session.flush()
        session.add(Competition(
            source_id=src.id, name="Champs", date_start=date(2026, 5, 1),
            venue_id=venue.id, discipline="Dressage", event_type="competition",
            tags='["discipline:dressage", "type:competition", "level:championship"]',
            first_seen_at=datetime.utcnow(), last_seen_at=datetime.utcnow(),
        ))
        session.add(Competition(
            source_id=src.id, name="County Show", date_start=date(2026, 5, 2),
            venue_id=venue.id, discipline=None, event_type="show",
            tags=None,
            first_seen_at=datetime.utcnow(), last_seen_at=datetime.utcnow(),
        ))
        await session.commit()


class TestTagsAndEventType:
    @pytest.mark.asyncio
    async def test_tags_deserialized_as_list(self):
        app = _get_app()
        await _seed_typed()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/competitions")
        comp = next(c for c in resp.json() if c["name"] == "Champs")
        assert comp["tags"] == ["discipline:dressage", "type:competition", "level:championship"]

    @pytest.mark.asyncio
    async def test_null_tags_become_empty_list(self):
        app = _get_app()
        await _seed_typed()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/competitions?event_type=show")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "County Show"
        assert data[0]["tags"] == []

    @pytest.mark.asyncio
    async def test_default_excludes_shows(self):
        app = _get_app()
        await _seed_typed()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/competitions")
        names = {c["name"] for c in resp.json()}
        assert names == {"Champs"}  # show excluded by default

    @pytest.mark.asyncio
    async def test_event_type_filter(self):
        app = _get_app()
        await _seed_typed()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/competitions?event_type=competition")
        names = {c["name"] for c in resp.json()}
        assert names == {"Champs"}


async def _seed_spectator():
    """Grassroots (compete only), county show (both), elite (watch only)."""
    async with TestSession() as session:
        src = Source(name="S", url="https://e.example", parser_key="t", enabled=True,
                     created_at=datetime.utcnow())
        session.add(src)
        await session.flush()
        venue = Venue(name="V", postcode="TE1 2ST")
        session.add(venue)
        await session.flush()
        rows = [
            ("Local Dressage", "competition", False),   # Compete only
            ("County Show", "competition", True),        # both
            ("Aachen CHIO", "show", True),               # Watch only
        ]
        for name, et, spec in rows:
            session.add(Competition(
                source_id=src.id, name=name, date_start=date(2026, 5, 1),
                venue_id=venue.id, event_type=et, spectator=spec,
                first_seen_at=datetime.utcnow(), last_seen_at=datetime.utcnow(),
            ))
        await session.commit()


class TestSpectator:
    @pytest.mark.asyncio
    async def test_compete_default_excludes_watch_only(self):
        app = _get_app()
        await _seed_spectator()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/competitions")  # Compete tab
        names = {c["name"] for c in resp.json()}
        assert names == {"Local Dressage", "County Show"}  # enterable competitions

    @pytest.mark.asyncio
    async def test_watch_returns_spectator_events(self):
        app = _get_app()
        await _seed_spectator()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/competitions?spectator=true")  # Watch tab
        data = resp.json()
        names = {c["name"] for c in data}
        assert names == {"County Show", "Aachen CHIO"}  # both spectator=true
        assert all(c["spectator"] for c in data)

    @pytest.mark.asyncio
    async def test_county_show_appears_in_both(self):
        app = _get_app()
        await _seed_spectator()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            compete = {c["name"] for c in (await client.get("/api/competitions")).json()}
            watch = {c["name"] for c in (await client.get("/api/competitions?spectator=true")).json()}
        assert "County Show" in compete and "County Show" in watch


# ---------------------------------------------------------------------------
# Hidden flag + effective-date sort
# ---------------------------------------------------------------------------
class TestHiddenAndSort:
    @pytest.mark.asyncio
    async def test_hidden_events_excluded(self):
        app = _get_app()
        async with TestSession() as session:
            src = Source(name="S", url="u", parser_key="p", enabled=True, created_at=datetime.utcnow())
            session.add(src)
            await session.flush()
            v = Venue(name="V")
            session.add(v)
            await session.flush()
            today = date.today()
            session.add(Competition(
                source_id=src.id, name="Visible Show", date_start=today + timedelta(days=3),
                venue_id=v.id, event_type="competition",
                first_seen_at=datetime.utcnow(), last_seen_at=datetime.utcnow(),
            ))
            session.add(Competition(
                source_id=src.id, name="Hidden Programme", date_start=today + timedelta(days=1),
                date_end=today + timedelta(days=400), venue_id=v.id, event_type="competition",
                hidden=True, first_seen_at=datetime.utcnow(), last_seen_at=datetime.utcnow(),
            ))
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/competitions")
        names = [c["name"] for c in resp.json()]
        assert "Visible Show" in names
        assert "Hidden Programme" not in names

    @pytest.mark.asyncio
    async def test_effective_date_sort_puts_today_above_stale_ongoing(self):
        """A stale-but-ongoing event must not sort above a real event happening
        today (it would under a plain date_start sort)."""
        app = _get_app()
        async with TestSession() as session:
            src = Source(name="S", url="u", parser_key="p", enabled=True, created_at=datetime.utcnow())
            session.add(src)
            await session.flush()
            v = Venue(name="V")
            session.add(v)
            await session.flush()
            today = date.today()
            # Stale ongoing (started 50d ago, ends in 5d) — span 55d, not hidden.
            session.add(Competition(
                source_id=src.id, name="Ongoing Stale", date_start=today - timedelta(days=50),
                date_end=today + timedelta(days=5), venue_id=v.id, event_type="competition",
                first_seen_at=datetime.utcnow(), last_seen_at=datetime.utcnow(),
            ))
            # Genuine one-day event happening today.
            session.add(Competition(
                source_id=src.id, name="Today Show", date_start=today, date_end=today,
                venue_id=v.id, event_type="competition",
                first_seen_at=datetime.utcnow(), last_seen_at=datetime.utcnow(),
            ))
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/competitions?date_from={date.today().isoformat()}")
        names = [c["name"] for c in resp.json()]
        assert names.index("Today Show") < names.index("Ongoing Stale")


# ---------------------------------------------------------------------------
# Tag filter (series / affiliation / qualifier pathways)
# ---------------------------------------------------------------------------
class TestTagFilter:
    async def _seed_two(self, session):
        src = Source(name="S", url="u", parser_key="p", enabled=True, created_at=datetime.utcnow())
        session.add(src)
        await session.flush()
        v = Venue(name="V")
        session.add(v)
        await session.flush()
        today = date.today()
        session.add(Competition(
            source_id=src.id, name="NSEA Champs Qualifier", date_start=today + timedelta(days=5),
            venue_id=v.id, event_type="competition", tags='["affiliation:nsea"]',
            first_seen_at=datetime.utcnow(), last_seen_at=datetime.utcnow(),
        ))
        session.add(Competition(
            source_id=src.id, name="BD Dressage", date_start=today + timedelta(days=6),
            venue_id=v.id, event_type="competition", tags='["affiliation:british-dressage"]',
            first_seen_at=datetime.utcnow(), last_seen_at=datetime.utcnow(),
        ))
        await session.commit()

    @pytest.mark.asyncio
    async def test_filter_by_tag(self):
        app = _get_app()
        async with TestSession() as session:
            await self._seed_two(session)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/competitions?tag=affiliation:nsea")
        assert [c["name"] for c in resp.json()] == ["NSEA Champs Qualifier"]

    @pytest.mark.asyncio
    async def test_malformed_tag_is_ignored(self):
        """A malformed tag must be rejected by the guard (not injected), and simply
        apply no tag filter rather than erroring."""
        app = _get_app()
        async with TestSession() as session:
            await self._seed_two(session)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/competitions", params={"tag": "% OR 1=1"})
        assert resp.status_code == 200
        assert len(resp.json()) == 2  # invalid token ignored → no filter
