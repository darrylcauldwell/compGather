"""Tests for the /api/venues/hire endpoint (Explore "Arena hire" mode).

A venue qualifies for the hire directory if it's seed-flagged with a hire_url,
or it lists upcoming venue_hire sessions. Uses an in-memory SQLite database.
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


async def _seed_hire_venues() -> None:
    """Seed four venues: seed-flagged hire, hire-via-events, plain, and no-coords."""
    soon = date.today() + timedelta(days=14)
    async with TestSession() as session:
        src = Source(name="S", url="https://e.com", parser_key="t", enabled=True,
                     created_at=datetime.utcnow())
        session.add(src)
        await session.flush()

        # A: seed-flagged with a hire_url (static-hire venue like Abbey Farm)
        a = Venue(name="Abbey Farm", postcode="DE4 2GL", latitude=53.1, longitude=-1.6,
                  hire_url="https://abbeyfarmequestrian.co.uk/arena-hire-2/")
        # B: no hire_url, but lists an upcoming venue_hire slot
        b = Venue(name="Slot Venue", postcode="LS1 1AA", latitude=53.8, longitude=-1.5)
        # C: only a competition — must NOT appear
        c = Venue(name="Comp Only", postcode="YO1 1AA", latitude=53.9, longitude=-1.0)
        # D: seed-flagged but no coords — excluded (can't pin on the map)
        d = Venue(name="No Coords Hire", postcode="ZZ1 1ZZ",
                  hire_url="https://example.com/hire")
        # E/F: the same venue two ways — a curated seed hire_url and an event-
        # derived record at the SAME postcode. The endpoint must collapse them to
        # one pin, keeping the curated arena-hire link over the single slot URL.
        e = Venue(name="Dupe (Curated)", postcode="PE1 1PE", latitude=52.5, longitude=-0.2,
                  hire_url="https://curated.example/arena-hire")
        f = Venue(name="Dupe Equestrian Centre", postcode="PE1 1PE", latitude=52.5, longitude=-0.2)
        for v in (a, b, c, d, e, f):
            session.add(v)
        await session.flush()

        session.add(Competition(source_id=src.id, name="Indoor Arena Hire", date_start=soon,
                                venue_id=b.id, event_type="venue_hire",
                                url="https://slot.example/book", first_seen_at=datetime.utcnow(),
                                last_seen_at=datetime.utcnow()))
        session.add(Competition(source_id=src.id, name="Arena Hire Slot", date_start=soon,
                                venue_id=f.id, event_type="venue_hire",
                                url="https://slots.example/book", first_seen_at=datetime.utcnow(),
                                last_seen_at=datetime.utcnow()))
        session.add(Competition(source_id=src.id, name="Summer Show", date_start=soon,
                                venue_id=c.id, event_type="competition",
                                url="https://comp.example", first_seen_at=datetime.utcnow(),
                                last_seen_at=datetime.utcnow()))
        await session.commit()


@pytest.mark.asyncio
async def test_hire_directory_lists_seed_and_event_venues():
    app = _get_app()
    await _seed_hire_venues()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/venues/hire")

    assert resp.status_code == 200
    by_name = {v["name"]: v for v in resp.json()}
    # Seed-flagged and event-derived hire venues appear …
    assert "Abbey Farm" in by_name
    assert "Slot Venue" in by_name
    # … a competition-only venue and a coord-less venue do not.
    assert "Comp Only" not in by_name
    assert "No Coords Hire" not in by_name


@pytest.mark.asyncio
async def test_hire_link_prefers_seed_url_then_slot_url():
    app = _get_app()
    await _seed_hire_venues()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/venues/hire")

    by_name = {v["name"]: v for v in resp.json()}
    assert by_name["Abbey Farm"]["hire_url"] == "https://abbeyfarmequestrian.co.uk/arena-hire-2/"
    assert by_name["Abbey Farm"]["has_slots"] is False
    # Event-derived venue surfaces the booking link from its hire slot.
    assert by_name["Slot Venue"]["hire_url"] == "https://slot.example/book"
    assert by_name["Slot Venue"]["has_slots"] is True


@pytest.mark.asyncio
async def test_hire_viewport_bbox_narrows_to_visible_region():
    app = _get_app()
    await _seed_hire_venues()
    # A box around Abbey Farm (53.1, -1.6) that excludes Slot Venue (53.8, -1.5).
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/venues/hire",
            params={"min_lat": 53.0, "max_lat": 53.5, "min_lng": -2.0, "max_lng": -1.0},
        )

    names = {v["name"] for v in resp.json()}
    assert "Abbey Farm" in names
    assert "Slot Venue" not in names


@pytest.mark.asyncio
async def test_hire_dedupes_same_postcode_preferring_curated():
    app = _get_app()
    await _seed_hire_venues()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/venues/hire")

    pe = [v for v in resp.json() if v["postcode"] == "PE1 1PE"]
    assert len(pe) == 1  # the two records collapse to a single pin
    assert pe[0]["hire_url"] == "https://curated.example/arena-hire"  # curated link wins
