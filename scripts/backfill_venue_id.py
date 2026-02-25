#!/usr/bin/env python3
"""One-off migration script: backfill venue_id on competitions table.

Run inside the Docker container after deploying the venue FK migration:
    docker exec compgather python scripts/backfill_venue_id.py

What it does:
1. For each competition with NULL venue_id, match venue_name → venues.name
2. Create venue rows for competition venue_names that don't match any venue
3. Set venue_id on all competitions
4. Populate venues.distance_miles from venue coordinates + home postcode
"""

import math
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DB_PATH = Path("data/compgather.db")


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles."""
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def main() -> None:
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    # Build venue name -> id lookup
    cur.execute("SELECT id, name FROM venues")
    venue_lookup: dict[str, int] = {name: vid for vid, name in cur.fetchall()}
    print(f"Loaded {len(venue_lookup)} existing venues")

    # Get all competitions that need venue_id
    cur.execute(
        "SELECT id, venue_name, venue_postcode, latitude, longitude "
        "FROM competitions WHERE venue_id IS NULL"
    )
    comps = cur.fetchall()
    print(f"Found {len(comps)} competitions with NULL venue_id")

    set_count = 0
    created_venues = 0
    for comp_id, venue_name, postcode, lat, lng in comps:
        if not venue_name:
            continue

        # Look up venue by name
        venue_id = venue_lookup.get(venue_name)

        if venue_id is None:
            # Create a new venue
            cur.execute(
                "INSERT INTO venues (name, postcode, latitude, longitude) "
                "VALUES (?, ?, ?, ?)",
                (venue_name, postcode, lat, lng),
            )
            venue_id = cur.lastrowid
            venue_lookup[venue_name] = venue_id
            created_venues += 1

        cur.execute(
            "UPDATE competitions SET venue_id = ? WHERE id = ?",
            (venue_id, comp_id),
        )
        set_count += 1

    conn.commit()
    print(f"Set venue_id on {set_count} competitions")
    print(f"Created {created_venues} new venue rows")

    # Verify
    cur.execute("SELECT COUNT(*) FROM competitions WHERE venue_id IS NULL")
    null_count = cur.fetchone()[0]
    print(f"Remaining NULL venue_ids: {null_count}")

    # Populate venues.distance_miles from venue coordinates + home postcode
    cur.execute("SELECT value FROM app_settings WHERE key = 'home_postcode'")
    row = cur.fetchone()
    home_lat, home_lng = None, None

    if row:
        home_postcode = row[0]
        # Find home coordinates: check if any venue has this postcode
        cur.execute(
            "SELECT latitude, longitude FROM venues "
            "WHERE postcode = ? AND latitude IS NOT NULL LIMIT 1",
            (home_postcode,),
        )
        home_row = cur.fetchone()
        if home_row:
            home_lat, home_lng = home_row
            print(f"\nHome postcode {home_postcode} -> ({home_lat:.4f}, {home_lng:.4f})")
        else:
            # Fallback: look in the old competition data
            cur.execute(
                "SELECT latitude, longitude FROM competitions "
                "WHERE venue_postcode = ? AND latitude IS NOT NULL LIMIT 1",
                (home_postcode,),
            )
            home_row = cur.fetchone()
            if home_row:
                home_lat, home_lng = home_row
                print(f"\nHome postcode {home_postcode} -> ({home_lat:.4f}, {home_lng:.4f}) (from competitions)")

    if home_lat is not None:
        cur.execute(
            "SELECT id, latitude, longitude FROM venues "
            "WHERE latitude IS NOT NULL"
        )
        distance_count = 0
        for vid, lat, lng in cur.fetchall():
            dist = _haversine(home_lat, home_lng, lat, lng)
            cur.execute("UPDATE venues SET distance_miles = ? WHERE id = ?", (dist, vid))
            distance_count += 1

        # Online/virtual venues get distance 0
        cur.execute(
            "UPDATE venues SET distance_miles = 0.0 "
            "WHERE LOWER(name) IN ('online', 'virtual') AND distance_miles IS NULL"
        )

        conn.commit()
        print(f"Calculated distance_miles for {distance_count} venues")
    else:
        print("\nCould not determine home coordinates — distances will be calculated on next app restart")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
