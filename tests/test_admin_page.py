"""Tests for the /admin page — focused on the source staleness flag.

A source that has events in the DB but none upcoming is "stale" (its fixtures
have all passed) and is flagged for refresh. Uses an in-memory SQLite DB and a
minimal app mounting only the pages router.
"""

from __future__ import annotations

import re
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


async def _seed():
    """Fresh source (future event), stale source (past only), unscanned source."""
    async with TestSession() as session:
        venue = Venue(name="Test Venue", latitude=51.5, longitude=-0.1)
        session.add(venue)
        await session.flush()

        fresh = Source(name="Fresh Source", url="https://fresh.example", enabled=True,
                       created_at=datetime.utcnow())
        stale = Source(name="Stale Source", url="https://stale.example", enabled=True,
                       created_at=datetime.utcnow())
        never = Source(name="Never Scanned", url="https://never.example", enabled=True,
                       created_at=datetime.utcnow())
        session.add_all([fresh, stale, never])
        await session.flush()

        today = date.today()
        session.add(Competition(
            source_id=fresh.id, venue_id=venue.id, name="Upcoming",
            date_start=today + timedelta(days=30), event_type="competition",
            first_seen_at=datetime.utcnow(), last_seen_at=datetime.utcnow(),
        ))
        session.add(Competition(
            source_id=stale.id, venue_id=venue.id, name="Bygone",
            date_start=today - timedelta(days=300), event_type="competition",
            first_seen_at=datetime.utcnow(), last_seen_at=datetime.utcnow(),
        ))
        await session.commit()
        return fresh.id, stale.id, never.id


@pytest.mark.asyncio
async def test_admin_flags_stale_sources():
    fresh_id, stale_id, never_id = await _seed()
    app = _get_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin")

    assert resp.status_code == 200
    html = resp.text
    norm = re.sub(r"\s+", " ", html)
    # Exactly one stale source -> one badge + a singular banner.
    assert html.count(">Stale</span>") == 1
    assert "1 source needs a refresh" in norm
    # The stale source's row carries the badge; the fresh one does not.
    assert "Stale Source" in html
    assert "Fresh Source" in html


@pytest.mark.asyncio
async def test_admin_no_banner_when_all_fresh():
    async with TestSession() as session:
        venue = Venue(name="V", latitude=1.0, longitude=1.0)
        session.add(venue)
        await session.flush()
        src = Source(name="Only Fresh", url="https://x.example", enabled=True,
                     created_at=datetime.utcnow())
        session.add(src)
        await session.flush()
        session.add(Competition(
            source_id=src.id, venue_id=venue.id, name="Soon",
            date_start=date.today() + timedelta(days=10), event_type="competition",
            first_seen_at=datetime.utcnow(), last_seen_at=datetime.utcnow(),
        ))
        await session.commit()

    app = _get_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin")

    assert resp.status_code == 200
    assert "a refresh" not in resp.text
    assert ">Stale</span>" not in resp.text
