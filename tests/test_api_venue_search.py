"""Tests for the /api/venues/search endpoint (the app's venue picker).

Returns venues matching a name substring or postcode prefix, restricted to
venues with at least one upcoming event, busiest first. Uses an in-memory
SQLite database.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.models import Competition, Source, Venue

TEST_ENGINE = create_async_engine(
    "sqlite+aiosqlite://",
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = async_sessionmaker(TEST_ENGINE, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _override_get_session():
    async with TestSession() as session:
        yield session


def _get_app():
    from fastapi import FastAPI

    from app.routers.pages import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = _override_get_session
    return app


async def _seed_venues() -> None:
    """Busy venue, quiet venue, past-only venue, hire-only venue, placeholder."""
    soon = date.today() + timedelta(days=14)
    past = date.today() - timedelta(days=30)
    async with TestSession() as session:
        src = Source(name="S", url="https://e.com", parser_key="t", enabled=True,
                     created_at=datetime.utcnow())
        session.add(src)
        await session.flush()

        keysoe = Venue(name="The College EC, Keysoe", postcode="MK44 2JP")
        quob = Venue(name="Quob Stables", postcode="SO30 2HQ")
        past_only = Venue(name="Keysoe Retired Venue", postcode="MK44 9ZZ")
        hire_only = Venue(name="Keysoe Hire Barn", postcode="MK44 8YY")
        placeholder = Venue(name="Tbc", postcode=None)
        for v in (keysoe, quob, past_only, hire_only, placeholder):
            session.add(v)
        await session.flush()

        def comp(venue, name, when, event_type="competition", hidden=False):
            return Competition(source_id=src.id, name=name, date_start=when,
                               venue_id=venue.id, event_type=event_type, hidden=hidden,
                               first_seen_at=datetime.utcnow(), last_seen_at=datetime.utcnow())

        session.add(comp(keysoe, "Keysoe International", soon))
        session.add(comp(keysoe, "Keysoe Unaffiliated SJ", soon))
        session.add(comp(keysoe, "Keysoe Hidden Dup", soon, hidden=True))
        session.add(comp(quob, "Quob Premier League", soon))
        session.add(comp(past_only, "Last Season Show", past))
        session.add(comp(hire_only, "Arena Hire", soon, event_type="venue_hire"))
        session.add(comp(placeholder, "Somewhere Someday", soon))
        await session.commit()


@pytest.mark.asyncio
async def test_search_matches_name_substring_busiest_first():
    app = _get_app()
    await _seed_venues()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/venues/search", params={"q": "keysoe"})

    assert resp.status_code == 200
    results = resp.json()
    names = [v["name"] for v in results]
    assert names[0] == "The College EC, Keysoe"  # 2 upcoming events, busiest first
    # Hidden events don't count toward the total.
    assert results[0]["event_count"] == 2
    # Past-only and hire-only venues are dead ends for the picker.
    assert "Keysoe Retired Venue" not in names
    assert "Keysoe Hire Barn" not in names


@pytest.mark.asyncio
async def test_search_matches_postcode_prefix():
    app = _get_app()
    await _seed_venues()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/venues/search", params={"q": "SO30"})

    names = [v["name"] for v in resp.json()]
    assert names == ["Quob Stables"]


@pytest.mark.asyncio
async def test_search_excludes_placeholder_venues():
    app = _get_app()
    await _seed_venues()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/venues/search", params={"q": "tb"})

    assert resp.json() == []


@pytest.mark.asyncio
async def test_search_rejects_short_query():
    app = _get_app()
    await _seed_venues()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/venues/search", params={"q": "k"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_neutralises_like_wildcards():
    app = _get_app()
    await _seed_venues()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/venues/search", params={"q": "%%"})

    # Wildcards are stripped, leaving a too-short term → empty, not everything.
    assert resp.json() == []
