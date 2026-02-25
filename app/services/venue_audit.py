"""Venue audit utilities - identify unmatched dynamic venues and consolidation candidates."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Venue
from app.seed_data import get_venue_seeds


async def find_unmatched_dynamic_venues(session: AsyncSession) -> dict:
    """Find all dynamic venues that don't match seed data venue or alias names.

    This helps identify:
    - New venues discovered by parsers not yet in seed data
    - Duplicate/variant names for existing venues
    - Consolidation candidates

    Returns dict with:
        - unmatched: list of (id, name) tuples (venues not in seed data)
        - matched: list of (id, name) tuples (venues matching seed data)
        - consolidation_candidates: dict of prefix -> list of venues (potential duplicates)
        - stats: dict with counts
    """

    # Get seed data reference sets
    seed_venues = set(get_venue_seeds().keys())
    seed_aliases = set()
    for data in get_venue_seeds().values():
        for alias in data.get("aliases", []):
            seed_aliases.add(alias)

    # Query all dynamic venues
    result = await session.execute(
        select(Venue.id, Venue.name)
        .where(Venue.source == "dynamic")
        .order_by(Venue.name)
    )
    dynamic_venues = result.all()

    # Classify each venue
    unmatched = []
    matched = []

    for vid, name in dynamic_venues:
        if name in seed_venues or name in seed_aliases:
            matched.append((vid, name))
        else:
            unmatched.append((vid, name))

    # Group unmatched venues by first word (prefix) to find consolidation candidates
    prefix_groups = {}
    for vid, name in unmatched:
        parts = name.split()
        prefix = parts[0] if parts else name

        if prefix not in prefix_groups:
            prefix_groups[prefix] = []
        prefix_groups[prefix].append((vid, name))

    # Filter to groups with 2+ venues (actual consolidation candidates)
    consolidation_candidates = {
        k: v for k, v in prefix_groups.items() if len(v) >= 2
    }
    consolidation_candidates = dict(
        sorted(consolidation_candidates.items(), key=lambda x: -len(x[1]))
    )

    return {
        "unmatched": unmatched,
        "matched": matched,
        "consolidation_candidates": consolidation_candidates,
        "stats": {
            "total_dynamic": len(dynamic_venues),
            "matched_to_seed": len(matched),
            "unmatched": len(unmatched),
            "consolidation_groups": len(consolidation_candidates),
            "match_percentage": round(100 * len(matched) / len(dynamic_venues), 1)
            if dynamic_venues
            else 0,
        },
    }
