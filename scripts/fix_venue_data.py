#!/usr/bin/env python3
"""One-off script to fix HIGH priority venue data quality issues.

Run inside the Docker container:
    docker exec compgather python scripts/fix_venue_data.py

What it does:
A) Fix NULL distance_miles on venues that have coordinates
B) Clear wrong coordinates on disambiguated venues, set correct postcodes
C) Resolve TBC/Tba/None competitions using postcodes from raw_extract
"""

import json
import math
import re
import sqlite3
import sys
from pathlib import Path

# Allow importing from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.parsers.utils import normalise_postcode  # noqa: E402

DB_PATH = Path("data/compgather.db")

# Disambiguated venue name pattern: "Brook Farm (TQ12)"
_DISAMBIGUATED_RE = re.compile(r"\(([A-Z]{1,2}\d[A-Z\d]?)\)$")

# Venue seed data loaded from JSON
_VENUE_SEEDS: dict[str, dict] = {}


def _load_seeds() -> None:
    """Lazily load seed data from venue_seeds.json."""
    global _VENUE_SEEDS
    try:
        from app.seed_data import get_venue_seeds
        _VENUE_SEEDS = get_venue_seeds()
    except ImportError:
        print("Warning: could not import get_venue_seeds")


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles."""
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _get_home_coords(cur: sqlite3.Cursor) -> tuple[float, float] | None:
    """Get home coordinates from app_settings + venues table."""
    cur.execute("SELECT value FROM app_settings WHERE key = 'home_postcode'")
    row = cur.fetchone()
    if not row:
        return None
    home_postcode = row[0]
    cur.execute(
        "SELECT latitude, longitude FROM venues "
        "WHERE postcode = ? AND latitude IS NOT NULL LIMIT 1",
        (home_postcode,),
    )
    home_row = cur.fetchone()
    if home_row:
        print(f"Home postcode {home_postcode} -> ({home_row[0]:.4f}, {home_row[1]:.4f})")
        return home_row
    return None


def step_a_fix_null_distances(cur: sqlite3.Cursor, conn: sqlite3.Connection) -> None:
    """Fix venues with coordinates but NULL distance_miles."""
    print("\n--- Step A: Fix NULL distance_miles ---")
    home = _get_home_coords(cur)
    if not home:
        print("Cannot determine home coordinates, skipping distance fix")
        return

    home_lat, home_lng = home
    cur.execute(
        "SELECT id, name, latitude, longitude FROM venues "
        "WHERE latitude IS NOT NULL AND distance_miles IS NULL"
    )
    rows = cur.fetchall()
    if not rows:
        print("No venues with NULL distance_miles found")
        return

    for vid, name, lat, lng in rows:
        dist = _haversine(home_lat, home_lng, lat, lng)
        cur.execute("UPDATE venues SET distance_miles = ? WHERE id = ?", (dist, vid))
        print(f"  {name}: {dist:.1f} mi")

    conn.commit()
    print(f"Fixed distance_miles on {len(rows)} venues")


def step_b_fix_disambiguated_venues(cur: sqlite3.Cursor, conn: sqlite3.Connection) -> None:
    """Clear wrong coordinates on disambiguated venues and set correct postcodes."""
    print("\n--- Step B: Fix disambiguated venues ---")
    _load_seeds()

    cur.execute("SELECT id, name, postcode, latitude, longitude FROM venues")
    all_venues = cur.fetchall()

    cleared = 0
    postcode_updated = 0
    for vid, name, postcode, lat, lng in all_venues:
        m = _DISAMBIGUATED_RE.search(name)
        if not m:
            continue

        # Check if this venue has a seed postcode
        seed_data = _VENUE_SEEDS.get(name, {})
        seed_pc = seed_data.get("postcode")

        changes = []

        # Update postcode from seed if missing or different
        if seed_pc and postcode != seed_pc:
            cur.execute("UPDATE venues SET postcode = ? WHERE id = ?", (seed_pc, vid))
            changes.append(f"postcode {postcode!r} -> {seed_pc!r}")
            postcode_updated += 1

        # Clear coordinates — will be re-geocoded from postcode at next startup
        if lat is not None:
            cur.execute(
                "UPDATE venues SET latitude = NULL, longitude = NULL, distance_miles = NULL "
                "WHERE id = ?",
                (vid,),
            )
            changes.append(f"cleared coords ({lat:.4f}, {lng:.4f})")
            cleared += 1

        if changes:
            print(f"  {name}: {', '.join(changes)}")

    conn.commit()
    print(f"Cleared coords on {cleared} disambiguated venues, updated {postcode_updated} postcodes")


def step_c_resolve_tbc_competitions(cur: sqlite3.Cursor, conn: sqlite3.Connection) -> None:
    """Resolve TBC/Tba/None competitions using postcodes from raw_extract."""
    print("\n--- Step C: Resolve TBC/Tba/None competitions ---")

    placeholder_names = {"tbc", "tba", "tbd", "various", "unknown", "none"}

    # Find placeholder venue IDs
    cur.execute("SELECT id, name FROM venues")
    tbc_venue_ids = []
    for vid, name in cur.fetchall():
        if name.strip().lower() in placeholder_names:
            tbc_venue_ids.append((vid, name))

    if not tbc_venue_ids:
        print("No placeholder venues found")
        return

    for vid, name in tbc_venue_ids:
        cur.execute(
            "SELECT COUNT(*) FROM competitions WHERE venue_id = ?", (vid,)
        )
        count = cur.fetchone()[0]
        print(f"  Placeholder venue '{name}' (id={vid}): {count} competitions")

    # Build postcode -> venue mapping (non-placeholder venues only)
    cur.execute("SELECT id, name, postcode FROM venues WHERE postcode IS NOT NULL")
    pc_to_venue: dict[str, tuple[int, str]] = {}
    pc_ambiguous: set[str] = set()
    for vid, name, postcode in cur.fetchall():
        if name.strip().lower() in placeholder_names:
            continue
        pc_key = postcode.strip().upper()
        if pc_key in pc_ambiguous:
            continue
        if pc_key in pc_to_venue:
            del pc_to_venue[pc_key]
            pc_ambiguous.add(pc_key)
        else:
            pc_to_venue[pc_key] = (vid, name)

    # For each competition at a placeholder venue, try to resolve by postcode
    tbc_ids = [vid for vid, _ in tbc_venue_ids]
    placeholders = ",".join("?" * len(tbc_ids))
    cur.execute(
        f"SELECT id, venue_id, raw_extract FROM competitions WHERE venue_id IN ({placeholders})",
        tbc_ids,
    )
    comps = cur.fetchall()

    resolved = 0
    for comp_id, venue_id, raw_extract in comps:
        if not raw_extract:
            continue
        try:
            data = json.loads(raw_extract)
        except (ValueError, TypeError):
            continue
        raw_pc = data.get("venue_postcode")
        if not raw_pc:
            continue
        clean_pc = normalise_postcode(raw_pc)
        if not clean_pc:
            continue
        pc_key = clean_pc.strip().upper()
        match = pc_to_venue.get(pc_key)
        if match:
            new_venue_id, venue_name = match
            cur.execute(
                "UPDATE competitions SET venue_id = ? WHERE id = ?",
                (new_venue_id, comp_id),
            )
            resolved += 1
            print(f"  Comp {comp_id}: {pc_key} -> '{venue_name}' (venue_id={new_venue_id})")

    conn.commit()
    print(f"Resolved {resolved} TBC competitions by postcode")

    # Check for empty placeholder venues that can be deleted
    for vid, name in tbc_venue_ids:
        cur.execute("SELECT COUNT(*) FROM competitions WHERE venue_id = ?", (vid,))
        remaining = cur.fetchone()[0]
        if remaining == 0:
            cur.execute("DELETE FROM venues WHERE id = ?", (vid,))
            # Clean up any aliases pointing to this venue
            cur.execute("DELETE FROM venue_aliases WHERE venue_id = ?", (vid,))
            conn.commit()
            print(f"  Deleted empty placeholder venue '{name}' (id={vid})")
        else:
            print(f"  Placeholder venue '{name}' still has {remaining} competitions")


def main() -> None:
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    step_a_fix_null_distances(cur, conn)
    step_b_fix_disambiguated_venues(cur, conn)
    step_c_resolve_tbc_competitions(cur, conn)

    # Summary
    print("\n--- Summary ---")
    cur.execute("SELECT COUNT(*) FROM venues")
    print(f"Total venues: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM venues WHERE latitude IS NOT NULL AND distance_miles IS NULL")
    print(f"Venues with coords but NULL distance: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM venues WHERE postcode IS NOT NULL AND latitude IS NULL")
    print(f"Venues with postcode but no coords: {cur.fetchone()[0]}")
    cur.execute(
        "SELECT COUNT(*) FROM competitions WHERE venue_id IN "
        "(SELECT id FROM venues WHERE LOWER(TRIM(name)) IN ('tbc','tba','tbd','none','unknown'))"
    )
    print(f"Competitions at placeholder venues: {cur.fetchone()[0]}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
