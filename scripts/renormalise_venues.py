#!/usr/bin/env python3
"""One-off script to re-normalise venue names after alias/suffix updates.

Runs inside the Docker container:
    docker exec compgather python scripts/renormalise_venues.py

What it does (post venue-FK migration):
1. Re-normalises venue names in the venues table
2. Merges duplicate venues (remaps competition venue_ids to the keeper)
3. Cleans up orphaned venue aliases
"""

import sqlite3
import sys
from pathlib import Path

# Allow importing from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.parsers.utils import disambiguate_venue, normalise_venue_name  # noqa: E402
from app.seed_data import get_venue_aliases  # noqa: E402

DB_PATH = Path("data/compgather.db")


def _resolve_name(name: str, postcode: str | None = None) -> str:
    """Normalise a venue name, apply alias resolution, and disambiguate generics.

    Alias values are themselves normalised (since they may contain suffixes
    that the updated suffix list now strips).
    If the resulting name is a known ambiguous venue name and a postcode is
    available, the outward code is appended for disambiguation.
    """
    normalised = normalise_venue_name(name)
    aliased = get_venue_aliases().get(normalised)
    if aliased:
        # Normalise the alias target too (it may have suffixes we now strip)
        normalised = normalise_venue_name(aliased)
    # Disambiguate generic names like "Rectory Farm" → "Rectory Farm (GL7)"
    return disambiguate_venue(normalised, postcode)


def main() -> None:
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    # --- Step 1: Re-normalise and merge venues table ---
    cur.execute("SELECT id, name, postcode, latitude, longitude FROM venues")
    venue_rows = cur.fetchall()

    # Group venues by their new canonical name (using postcode for disambiguation)
    canonical_groups: dict[str, list[tuple]] = {}
    for vid, name, postcode, lat, lng in venue_rows:
        canonical = _resolve_name(name, postcode)
        canonical_groups.setdefault(canonical, []).append(
            (vid, name, postcode, lat, lng)
        )

    renames = sum(
        1 for g in canonical_groups.values()
        if len(g) == 1 and g[0][1] != _resolve_name(g[0][1], g[0][2])
    )
    merges = sum(len(g) - 1 for g in canonical_groups.values() if len(g) > 1)
    print(f"Venues table: {renames} renames, {merges} duplicates to merge")

    all_delete_ids: list[int] = []
    keeper_updates: list[tuple] = []  # (canonical, postcode, lat, lng, keeper_id)
    # Map deleted venue_id -> keeper venue_id (for FK remapping)
    venue_id_map: dict[int, int] = {}

    for canonical, group in canonical_groups.items():
        # Pick the "best" row: prefer one whose name already matches canonical
        # (avoids UNIQUE conflict when seed already created the canonical venue),
        # then prefer coords, then postcode
        group.sort(
            key=lambda r: (r[1] == canonical, r[3] is not None, r[2] is not None),
            reverse=True,
        )
        keeper_id, keeper_name, keeper_pc, keeper_lat, keeper_lng = group[0]

        # Merge data from others into keeper
        best_pc = keeper_pc
        best_lat = keeper_lat
        best_lng = keeper_lng
        for vid, _, pc, lat, lng in group[1:]:
            if not best_pc and pc:
                best_pc = pc
            if best_lat is None and lat is not None:
                best_lat = lat
                best_lng = lng
            all_delete_ids.append(vid)
            venue_id_map[vid] = keeper_id

        # Only update keeper if something changed
        if (keeper_name != canonical or best_pc != keeper_pc
                or best_lat != keeper_lat or best_lng != keeper_lng):
            keeper_updates.append((canonical, best_pc, best_lat, best_lng, keeper_id))

    # Remap competition venue_ids that point to deleted venues
    remapped = 0
    for old_id, new_id in venue_id_map.items():
        cur.execute(
            "UPDATE competitions SET venue_id = ? WHERE venue_id = ?",
            (new_id, old_id),
        )
        remapped += cur.rowcount

    # Remap venue aliases that point to deleted venues
    for old_id, new_id in venue_id_map.items():
        cur.execute(
            "UPDATE venue_aliases SET venue_id = ? WHERE venue_id = ?",
            (new_id, old_id),
        )

    # Delete duplicate venues
    if all_delete_ids:
        placeholders = ",".join("?" * len(all_delete_ids))
        cur.execute(
            f"DELETE FROM venues WHERE id IN ({placeholders})", all_delete_ids
        )

    # Then rename/update keepers (no UNIQUE conflicts now)
    for canonical, pc, lat, lng, kid in keeper_updates:
        cur.execute(
            "UPDATE venues SET name = ?, postcode = ?, latitude = ?, longitude = ? "
            "WHERE id = ?",
            (canonical, pc, lat, lng, kid),
        )

    conn.commit()
    print(f"Deleted {len(all_delete_ids)} duplicate venue rows, "
          f"updated {len(keeper_updates)} keepers, "
          f"remapped {remapped} competition FKs")

    # --- Step 2: Clean up orphaned venue aliases ---
    orphan_aliases = cur.execute(
        "DELETE FROM venue_aliases WHERE venue_id NOT IN (SELECT id FROM venues)"
    ).rowcount
    conn.commit()
    if orphan_aliases:
        print(f"Cleaned up {orphan_aliases} orphaned venue aliases")

    # --- Step 3: Summary ---
    cur.execute("SELECT COUNT(*) FROM venues")
    venue_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM competitions WHERE venue_id IS NULL")
    null_venue_count = cur.fetchone()[0]
    print(f"\nVenues: {venue_count}")
    print(f"Competitions with NULL venue_id: {null_venue_count}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
