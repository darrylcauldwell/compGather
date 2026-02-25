"""Tests for the venue matching service."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import Venue, VenueAlias
from app.services.venue_matcher import (
    VenueIndex,
    VenueMatch,
    _is_placeholder_name,
    match_venue,
    migrate_hardcoded_aliases,
)


@pytest_asyncio.fixture
async def session():
    """Create an in-memory SQLite session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as sess:
        yield sess

    await engine.dispose()


async def _seed_venues(session: AsyncSession) -> dict[str, int]:
    """Insert test venues and return {name: id} mapping."""
    venues = [
        Venue(name="Hickstead", postcode="BN6 9NS", latitude=50.93, longitude=-0.18),
        Venue(name="Oatridge", postcode="EH52 6NH", latitude=55.93, longitude=-3.56),
        Venue(name="Brook Farm", postcode="RM4 1EJ", latitude=51.65, longitude=0.18),
        Venue(name="Greenlands", postcode="CA4 0RR", latitude=54.85, longitude=-2.85),
        Venue(name="Mount Ballan", postcode="NP26 5XP", latitude=51.58, longitude=-2.78),
    ]
    for v in venues:
        session.add(v)
    await session.flush()
    return {v.name: v.id for v in venues}


async def _seed_aliases(session: AsyncSession, venue_ids: dict[str, int]) -> None:
    """Insert test aliases."""
    aliases = [
        VenueAlias(alias="All England Show Jumping Course", venue_id=venue_ids["Hickstead"], source="migrated"),
        VenueAlias(alias="The Scottish National", venue_id=venue_ids["Oatridge"], source="migrated"),
        VenueAlias(alias="Greenlands Arenas", venue_id=venue_ids["Greenlands"], source="migrated"),
    ]
    for a in aliases:
        session.add(a)
    await session.flush()


# ---------------------------------------------------------------------------
# VenueIndex tests
# ---------------------------------------------------------------------------
class TestVenueIndex:
    @pytest.mark.asyncio
    async def test_build_and_exact_match(self, session):
        venue_ids = await _seed_venues(session)
        await _seed_aliases(session, venue_ids)

        index = VenueIndex()
        await index.build(session)

        assert index.exact_match("Hickstead") == venue_ids["Hickstead"]
        assert index.exact_match("hickstead") == venue_ids["Hickstead"]
        assert index.exact_match("NonExistent") is None

    @pytest.mark.asyncio
    async def test_alias_match(self, session):
        venue_ids = await _seed_venues(session)
        await _seed_aliases(session, venue_ids)

        index = VenueIndex()
        await index.build(session)

        assert index.alias_match("All England Show Jumping Course") == venue_ids["Hickstead"]
        assert index.alias_match("The Scottish National") == venue_ids["Oatridge"]
        assert index.alias_match("Not An Alias") is None

    @pytest.mark.asyncio
    async def test_register_venue(self, session):
        index = VenueIndex()
        await index.build(session)

        index.register_venue(999, "New Place", postcode="AB1 2CD")
        assert index.exact_match("New Place") == 999
        data = index.get_venue_data(999)
        assert data["postcode"] == "AB1 2CD"

    @pytest.mark.asyncio
    async def test_postcode_match_unique(self, session):
        venue_ids = await _seed_venues(session)

        index = VenueIndex()
        await index.build(session)

        # BN6 9NS is only used by Hickstead
        assert index.postcode_match("BN6 9NS") == venue_ids["Hickstead"]
        assert index.postcode_match("bn6 9ns") == venue_ids["Hickstead"]

    @pytest.mark.asyncio
    async def test_postcode_match_no_match(self, session):
        await _seed_venues(session)

        index = VenueIndex()
        await index.build(session)

        assert index.postcode_match("ZZ1 1ZZ") is None

    @pytest.mark.asyncio
    async def test_postcode_match_ambiguous(self, session):
        """Two venues with same postcode returns None (ambiguous)."""
        v1 = Venue(name="Arena A", postcode="AB1 2CD")
        v2 = Venue(name="Arena B", postcode="AB1 2CD")
        session.add_all([v1, v2])
        await session.flush()

        index = VenueIndex()
        await index.build(session)

        assert index.postcode_match("AB1 2CD") is None


# ---------------------------------------------------------------------------
# _is_placeholder_name tests
# ---------------------------------------------------------------------------
class TestIsPlaceholderName:
    def test_tbc(self):
        assert _is_placeholder_name("Tbc") is True
        assert _is_placeholder_name("TBC") is True

    def test_tba(self):
        assert _is_placeholder_name("TBA") is True

    def test_various(self):
        assert _is_placeholder_name("Various") is True

    def test_online_is_not_placeholder(self):
        assert _is_placeholder_name("Online") is False

    def test_real_name(self):
        assert _is_placeholder_name("Hickstead") is False

    def test_empty(self):
        assert _is_placeholder_name("") is False


# ---------------------------------------------------------------------------
# match_venue tests
# ---------------------------------------------------------------------------
class TestMatchVenue:
    @pytest.mark.asyncio
    async def test_exact_match_path(self, session):
        venue_ids = await _seed_venues(session)

        index = VenueIndex()
        await index.build(session)

        result = await match_venue(
            session, index,
            normalised_name="Hickstead",
            raw_name="HICKSTEAD",
        )
        assert result.match_type == "exact"
        assert result.venue_name == "Hickstead"
        assert result.confidence == 1.0
        assert result.venue_id == venue_ids["Hickstead"]

    @pytest.mark.asyncio
    async def test_alias_match_path(self, session):
        venue_ids = await _seed_venues(session)
        await _seed_aliases(session, venue_ids)

        index = VenueIndex()
        await index.build(session)

        result = await match_venue(
            session, index,
            normalised_name="All England Show Jumping Course",
            raw_name="ALL ENGLAND SHOW JUMPING COURSE",
        )
        assert result.match_type == "alias"
        assert result.venue_name == "Hickstead"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_tbc_resolved_by_postcode(self, session):
        """TBC venue with a postcode matching a known venue should resolve."""
        venue_ids = await _seed_venues(session)

        index = VenueIndex()
        await index.build(session)

        result = await match_venue(
            session, index,
            normalised_name="Tbc",
            raw_name="TBC",
            postcode="BN6 9NS",  # Hickstead's postcode
        )
        assert result.match_type == "postcode"
        assert result.venue_name == "Hickstead"
        assert result.confidence == 0.95
        assert result.venue_id == venue_ids["Hickstead"]

    @pytest.mark.asyncio
    async def test_tbc_without_postcode_creates_new(self, session):
        """TBC venue with no postcode creates a new venue."""
        await _seed_venues(session)

        index = VenueIndex()
        await index.build(session)

        result = await match_venue(
            session, index,
            normalised_name="Tbc",
            raw_name="TBC",
        )
        assert result.match_type == "new"
        assert result.venue_name == "Tbc"

    @pytest.mark.asyncio
    async def test_no_match_creates_new_venue(self, session):
        """Completely unknown name should create a new venue."""
        await _seed_venues(session)

        index = VenueIndex()
        await index.build(session)

        result = await match_venue(
            session, index,
            normalised_name="Completely Unknown Venue",
            raw_name="COMPLETELY UNKNOWN VENUE",
            postcode="ZZ1 1ZZ",
        )
        assert result.match_type == "new"
        assert result.venue_name == "Completely Unknown Venue"
        assert result.confidence == 0.0

        # Should exist in DB now
        venue = (
            await session.execute(
                select(Venue).where(Venue.name == "Completely Unknown Venue")
            )
        ).scalar_one_or_none()
        assert venue is not None
        assert venue.postcode == "ZZ1 1ZZ"

    @pytest.mark.asyncio
    async def test_new_venue_added_to_index(self, session):
        """After creating a new venue, it should be findable in the index."""
        await _seed_venues(session)

        index = VenueIndex()
        await index.build(session)

        await match_venue(
            session, index,
            normalised_name="Brand New Place",
            raw_name="Brand New Place",
        )

        # Second call should exact-match
        result = await match_venue(
            session, index,
            normalised_name="Brand New Place",
            raw_name="Brand New Place",
        )
        assert result.match_type == "exact"


# ---------------------------------------------------------------------------
# migrate_hardcoded_aliases tests
# ---------------------------------------------------------------------------
class TestMigrateHardcodedAliases:
    @pytest.mark.asyncio
    async def test_migrates_aliases(self, session):
        await migrate_hardcoded_aliases(session)

        # Should have created entries
        count = len(
            (await session.execute(select(VenueAlias))).scalars().all()
        )
        assert count > 0

        # Check a specific alias
        alias = (
            await session.execute(
                select(VenueAlias).where(
                    VenueAlias.alias == "All England Show Jumping Course"
                )
            )
        ).scalar_one_or_none()
        assert alias is not None
        assert alias.source == "migrated"

        # Canonical venue should exist
        venue = await session.get(Venue, alias.venue_id)
        assert venue.name == "Hickstead"

    @pytest.mark.asyncio
    async def test_idempotent(self, session):
        await migrate_hardcoded_aliases(session)
        count1 = len(
            (await session.execute(select(VenueAlias))).scalars().all()
        )

        await migrate_hardcoded_aliases(session)
        count2 = len(
            (await session.execute(select(VenueAlias))).scalars().all()
        )

        assert count1 == count2
