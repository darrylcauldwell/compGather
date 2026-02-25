"""Match-first venue resolution.

Match incoming venue names against known venues using exact match, alias
lookup, and postcode resolution for placeholders. Unmatched names create
new venues — use scan observability to iteratively improve seed data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Venue, VenueAlias

logger = logging.getLogger(__name__)


@dataclass
class VenueMatch:
    venue_id: int | None
    venue_name: str
    confidence: float
    match_type: str  # "exact" | "alias" | "postcode" | "new"
    postcode: str | None = None
    lat: float | None = None
    lng: float | None = None


class VenueIndex:
    """In-memory index of known venues and aliases for fast lookup."""

    def __init__(self):
        self._venues: dict[str, int] = {}  # lowercase name -> venue_id
        self._aliases: dict[str, int] = {}  # lowercase alias -> venue_id
        self._venue_data: dict[int, dict] = {}  # venue_id -> {name, postcode, lat, lng}
        self._postcode_to_venues: dict[str, list[int]] = {}  # upper postcode -> [venue_ids]

    async def build(self, session: AsyncSession) -> None:
        """Load all venues and aliases from the database."""
        venues = (await session.execute(select(Venue))).scalars().all()
        for v in venues:
            self._venues[v.name.lower()] = v.id
            self._venue_data[v.id] = {
                "name": v.name,
                "postcode": v.postcode,
                "lat": v.latitude,
                "lng": v.longitude,
            }
            if v.postcode:
                pc_key = v.postcode.strip().upper()
                self._postcode_to_venues.setdefault(pc_key, []).append(v.id)

        aliases = (await session.execute(select(VenueAlias))).scalars().all()
        for a in aliases:
            self._aliases[a.alias.lower()] = a.venue_id

        logger.info(
            "VenueIndex built: %d venues, %d aliases",
            len(self._venues),
            len(self._aliases),
        )

    def exact_match(self, name: str) -> int | None:
        """Return venue_id if name matches a known venue exactly."""
        return self._venues.get(name.lower())

    def alias_match(self, name: str) -> int | None:
        """Return venue_id if name matches a known alias exactly."""
        return self._aliases.get(name.lower())

    def postcode_match(self, postcode: str) -> int | None:
        """Return venue_id if exactly one venue has this postcode."""
        pc_key = postcode.strip().upper()
        ids = self._postcode_to_venues.get(pc_key, [])
        if len(ids) == 1:
            return ids[0]
        return None

    def get_venue_data(self, venue_id: int) -> dict | None:
        """Return {name, postcode, lat, lng} for a venue_id."""
        return self._venue_data.get(venue_id)

    def register_venue(self, venue_id: int, name: str, postcode: str | None = None,
                       lat: float | None = None, lng: float | None = None) -> None:
        """Add a newly created venue to the index."""
        self._venues[name.lower()] = venue_id
        self._venue_data[venue_id] = {
            "name": name,
            "postcode": postcode,
            "lat": lat,
            "lng": lng,
        }


_PLACEHOLDER_NAMES = {"tbc", "tba", "tbd", "various", "unknown"}
_ONLINE_VENUE_NAMES = {"zoom", "teams", "microsoft teams", "google meet", "skype", "webinar"}


def _is_placeholder_name(name: str) -> bool:
    """Return True if the venue name is a placeholder (TBC, Online, etc.)."""
    return name.strip().lower() in _PLACEHOLDER_NAMES


async def match_venue(
    session: AsyncSession,
    index: VenueIndex,
    normalised_name: str,
    raw_name: str,
    postcode: str | None = None,
    parser_lat: float | None = None,
    parser_lng: float | None = None,
) -> VenueMatch:
    """Match a venue name against known venues.

    Returns VenueMatch with the best resolution:
    - exact match on venues.name -> confidence 1.0
    - alias match on venue_aliases.alias -> confidence 1.0
    - postcode match for placeholders (TBC) -> confidence 0.95
    - no match -> create new venue
    """
    # 0. Virtual venue names (Zoom, Teams, etc.) -> "Online"
    if normalised_name.strip().lower() in _ONLINE_VENUE_NAMES:
        normalised_name = "Online"

    # 1. Postcode-based resolution for placeholder names ("Tbc", "Tba", etc.)
    #    Checked FIRST so placeholders never accidentally match a real venue or alias.
    if _is_placeholder_name(normalised_name) and postcode:
        venue_id = index.postcode_match(postcode)
        if venue_id is not None:
            data = index.get_venue_data(venue_id)
            if data:
                logger.info(
                    "Venue resolved from postcode: '%s' (%s) -> '%s'",
                    normalised_name, postcode, data["name"],
                )
                return VenueMatch(
                    venue_id=venue_id,
                    venue_name=data["name"],
                    confidence=0.95,
                    match_type="postcode",
                    postcode=data.get("postcode"),
                    lat=data.get("lat"),
                    lng=data.get("lng"),
                )

    # 2. Exact match on venue name
    venue_id = index.exact_match(normalised_name)
    if venue_id is not None:
        data = index.get_venue_data(venue_id)
        return VenueMatch(
            venue_id=venue_id,
            venue_name=data["name"],
            confidence=1.0,
            match_type="exact",
            postcode=data.get("postcode"),
            lat=data.get("lat"),
            lng=data.get("lng"),
        )

    # 3. Alias match
    venue_id = index.alias_match(normalised_name)
    if venue_id is not None:
        data = index.get_venue_data(venue_id)
        if data:
            return VenueMatch(
                venue_id=venue_id,
                venue_name=data["name"],
                confidence=1.0,
                match_type="alias",
                postcode=data.get("postcode"),
                lat=data.get("lat"),
                lng=data.get("lng"),
            )
        logger.warning("Alias match: venue_id=%d not found in index for '%s'", venue_id, normalised_name)

    # 4. No match — create new venue
    venue = Venue(name=normalised_name, postcode=postcode)
    session.add(venue)
    await session.flush()  # get the ID
    index.register_venue(venue.id, normalised_name, postcode=postcode)
    logger.info("New venue created: '%s'", normalised_name)

    return VenueMatch(
        venue_id=venue.id,
        venue_name=normalised_name,
        confidence=0.0,
        match_type="new",
        postcode=postcode,
    )


async def migrate_hardcoded_aliases(session: AsyncSession) -> None:
    """Migrate venue aliases from venue_seeds.json to the venue_aliases table.

    Idempotent: skips aliases that already exist.
    Creates canonical venues if they don't exist yet.
    """
    from app.seed_data import get_venue_aliases

    migrated = 0
    for alias_name, canonical_name in get_venue_aliases().items():
        # Ensure canonical venue exists
        venue = (
            await session.execute(
                select(Venue).where(Venue.name == canonical_name)
            )
        ).scalar_one_or_none()

        if not venue:
            venue = Venue(name=canonical_name)
            session.add(venue)
            await session.flush()

        # Create alias if it doesn't exist
        existing = (
            await session.execute(
                select(VenueAlias).where(VenueAlias.alias == alias_name)
            )
        ).scalar_one_or_none()

        if not existing:
            session.add(VenueAlias(
                alias=alias_name,
                venue_id=venue.id,
                source="migrated",
            ))
            migrated += 1

    await session.commit()
    logger.info("Migrated %d aliases from hardcoded dict to venue_aliases table", migrated)


async def backfill_tbc_venues(session: AsyncSession) -> None:
    """Resolve existing placeholder-venue competitions using postcode lookup.

    Two strategies:
    1. If the TBC venue itself has a postcode matching exactly one real venue,
       reassign ALL its competitions to that venue.
    2. For remaining TBC competitions, extract venue_postcode from raw_extract
       JSON and match individually.

    Idempotent: only touches competitions whose venue is a placeholder.
    """
    import json as _json

    from app.models import Competition
    from app.parsers.utils import normalise_postcode

    placeholder_names = {"tbc", "tba", "tbd", "various", "unknown", "none"}

    # Build postcode -> venue mapping (non-placeholder venues only)
    all_venues = (await session.execute(
        select(Venue).where(Venue.postcode != None)
    )).scalars().all()

    pc_to_venue: dict[str, Venue] = {}
    pc_ambiguous: set[str] = set()
    for v in all_venues:
        if v.name.strip().lower() in placeholder_names:
            continue
        pc_key = v.postcode.strip().upper()
        if pc_key in pc_ambiguous:
            continue
        if pc_key in pc_to_venue:
            del pc_to_venue[pc_key]
            pc_ambiguous.add(pc_key)
        else:
            pc_to_venue[pc_key] = v

    # Find all placeholder venues
    all_placeholder_venues = (await session.execute(
        select(Venue)
    )).scalars().all()
    tbc_venue_ids = {
        v.id for v in all_placeholder_venues
        if v.name.strip().lower() in placeholder_names
    }

    if not tbc_venue_ids:
        logger.info("TBC backfill: no placeholder venues found")
        return

    fixed = 0

    # Strategy 1: TBC venues whose own postcode matches a real venue
    for v in all_placeholder_venues:
        if v.id not in tbc_venue_ids or not v.postcode:
            continue
        pc_key = v.postcode.strip().upper()
        real_venue = pc_to_venue.get(pc_key)
        if not real_venue:
            continue
        comps = (await session.execute(
            select(Competition).where(Competition.venue_id == v.id)
        )).scalars().all()
        for comp in comps:
            comp.venue_id = real_venue.id
            fixed += 1

    # Strategy 2: per-competition postcode from raw_extract
    remaining_comps = (await session.execute(
        select(Competition).where(Competition.venue_id.in_(tbc_venue_ids))
    )).scalars().all()

    for comp in remaining_comps:
        if not comp.raw_extract:
            continue
        try:
            data = _json.loads(comp.raw_extract)
        except (ValueError, TypeError):
            continue
        raw_pc = data.get("venue_postcode")
        if not raw_pc:
            continue
        clean_pc = normalise_postcode(raw_pc)
        if not clean_pc:
            continue
        pc_key = clean_pc.strip().upper()
        real_venue = pc_to_venue.get(pc_key)
        if real_venue:
            comp.venue_id = real_venue.id
            fixed += 1

    if fixed:
        await session.commit()
        logger.info("TBC backfill: resolved %d competitions by postcode", fixed)
    else:
        logger.info("TBC backfill: no resolvable TBC competitions found")
