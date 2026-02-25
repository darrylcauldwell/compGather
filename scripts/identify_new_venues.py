#!/usr/bin/env python3
"""Phase 1: Identify new venues in the database not yet in venue_seeds.json.

This script:
1. Queries the API for all future competitions
2. Loads all venues from venue_seeds.json
3. Identifies "new" venues (in API but not in seeds)
4. Filters to future competitions only
5. Excludes online/virtual venues
6. Generates a manifest for Phase 2 web crawling
"""

import httpx
import json
from datetime import date
from pathlib import Path
from collections import defaultdict

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.seed_data import get_venue_seeds


async def identify_new_venues():
    """Identify venues in API not in venue_seeds.json."""
    # Load seed venue names (case-insensitive set)
    seed_venues = get_venue_seeds()
    seed_names_lower = {name.lower() for name in seed_venues.keys()}
    print(f"Total venues in seed data: {len(seed_names_lower)}")

    # Fetch all competitions from API
    base_url = "http://localhost:8001/api/competitions"
    limit = 500
    offset = 0
    all_competitions = []

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            print(f"Fetching competitions: offset={offset}")
            response = await client.get(base_url, params={"limit": limit, "offset": offset})
            response.raise_for_status()
            data = response.json()
            if not data:
                break
            all_competitions.extend(data)
            offset += limit

    print(f"Total competitions from API: {len(all_competitions)}")

    # Filter to future competitions and group by venue
    today = date.today()
    venues_with_comps: dict[str, list[dict]] = defaultdict(list)

    for comp in all_competitions:
        date_start = comp.get("date_start")
        if not date_start:
            continue
        comp_date = date.fromisoformat(date_start)
        if comp_date < today:
            continue

        venue_name = comp.get("venue_name")
        if venue_name:
            venues_with_comps[venue_name].append(comp)

    print(f"Venues with future competitions: {len(venues_with_comps)}")

    # Identify new venues (not in seed data)
    new_venues = []

    for venue_name, comps in venues_with_comps.items():
        # Skip if in seed data (case-insensitive)
        if venue_name.lower() in seed_names_lower:
            continue

        # Skip online/virtual venues
        if venue_name.lower() in {
            "online", "zoom", "teams", "microsoft teams",
            "google meet", "skype", "webinar", "virtual", "tbc", "tba", "tbd"
        }:
            continue

        # Get sample URLs and competition names
        sample_urls = [c.get("url") for c in comps[:3] if c.get("url")]
        sample_names = [c.get("name") for c in comps[:2]]

        # Get postcode if available
        postcode = None
        lat = None
        lng = None
        for comp in comps:
            if comp.get("venue_postcode"):
                postcode = comp["venue_postcode"]
            if comp.get("latitude"):
                lat = comp["latitude"]
            if comp.get("longitude"):
                lng = comp["longitude"]

        new_venues.append({
            "name": venue_name,
            "postcode": postcode,
            "lat": lat,
            "lng": lng,
            "future_competition_count": len(comps),
            "sample_urls": sample_urls,
            "sample_competition_names": sample_names,
        })

    print(f"\nNew venues (not in seeds): {len(new_venues)}")

    # Filter to venues with some data to work with
    new_venues_with_context = [
        v for v in new_venues
        if v.get("postcode") or v.get("lat") or v.get("sample_urls")
    ]
    print(f"New venues with context (postcode/coords/URLs): {len(new_venues_with_context)}")

    # Sort by future competition count (descending)
    new_venues_with_context.sort(
        key=lambda v: v["future_competition_count"],
        reverse=True
    )

    # Save manifest
    manifest_path = Path(__file__).parent / "new_venues_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump({
            "total_new_venues": len(new_venues),
            "total_with_context": len(new_venues_with_context),
            "generated_at": date.today().isoformat(),
            "venues": new_venues_with_context[:100],  # Limit to 100 for initial batch
        }, f, indent=2)

    print(f"\nManifest saved to: {manifest_path}")
    print(f"\nFirst 10 new venues to validate:")
    for i, v in enumerate(new_venues_with_context[:10], 1):
        print(f"  {i}. {v['name']}: postcode={v['postcode']}, "
              f"coords=({v['lat']},{v['lng']}), {v['future_competition_count']} future comps")


if __name__ == "__main__":
    import asyncio
    asyncio.run(identify_new_venues())
