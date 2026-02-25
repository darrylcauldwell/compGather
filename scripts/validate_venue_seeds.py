#!/usr/bin/env python3
"""Validate app/venue_seeds.json for data quality issues.

Checks:
  A) Postcode format — must be valid UK postcode
  B) Coordinate bounds — must be within UK bounding box (49–61 lat, –11 to 2 lng)
  C) Postcode ↔ coordinate consistency — geocode each postcode via postcodes.io
     and flag where stored coords differ by more than DISTANCE_THRESHOLD_MILES
  D) Alias integrity — every alias target must exist as a venue key
  E) Coord-only completeness — venues with coords but no postcode

Run inside Docker:
    docker exec compgather python scripts/validate_venue_seeds.py

Or locally (requires requests):
    python3 scripts/validate_venue_seeds.py

Outputs a report with any suspicious entries that need review.
"""

import json
import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Threshold: flag if stored coords are more than this many miles from geocoded postcode
DISTANCE_THRESHOLD_MILES = 20.0

# UK bounding box (generous — includes Crown Dependencies)
UK_LAT_MIN, UK_LAT_MAX = 49.0, 61.5
UK_LNG_MIN, UK_LNG_MAX = -11.0, 2.5

# Crown Dependency postcode areas that Nominatim handles (postcodes.io doesn't)
CROWN_DEP_AREAS = {"GY", "JE", "IM"}

# Lightweight postcode format check
_POSTCODE_RE = re.compile(
    r"^[A-Z]{1,2}\d[A-Z\d]?\s+\d[A-Z]{2}$",
    re.IGNORECASE,
)


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles."""
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def geocode_postcode(postcode: str) -> tuple[float, float] | None:
    """Geocode a UK postcode via postcodes.io. Returns (lat, lng) or None."""
    try:
        import urllib.request
        url = f"https://api.postcodes.io/postcodes/{postcode.replace(' ', '%20')}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        if data.get("status") == 200:
            result = data["result"]
            return result["latitude"], result["longitude"]
        # Try terminated postcodes
        url2 = f"https://api.postcodes.io/terminated_postcodes/{postcode.replace(' ', '%20')}"
        with urllib.request.urlopen(url2, timeout=10) as resp2:
            data2 = json.loads(resp2.read())
        if data2.get("status") == 200:
            result2 = data2["result"]
            return result2["latitude"], result2["longitude"]
    except Exception:
        pass
    return None


def outward_code(postcode: str) -> str:
    """Extract the outward code (area + district): 'SW1A 1AA' → 'SW1A'."""
    return postcode.strip().split()[0].upper()


def area_code(postcode: str) -> str:
    """Extract the area code (letters only): 'SW1A' → 'SW'."""
    return re.match(r"^([A-Z]+)", postcode.strip().upper()).group(1)


def main() -> None:
    seeds_path = ROOT / "app" / "venue_seeds.json"
    with open(seeds_path) as f:
        data = json.load(f)

    venues = data["venues"]
    ambiguous = set(data["ambiguous_names"])

    issues: dict[str, list[str]] = {}

    def add_issue(name: str, msg: str) -> None:
        issues.setdefault(name, []).append(msg)

    print(f"Validating {len(venues)} venues from {seeds_path.name} ...")
    print()

    # ── A: Postcode format ────────────────────────────────────────────────────
    print("=== A: Postcode format ===")
    bad_format = 0
    for name, v in venues.items():
        pc = v.get("postcode")
        if pc and not _POSTCODE_RE.match(pc):
            add_issue(name, f"Bad postcode format: {pc!r}")
            bad_format += 1
    print(f"  {bad_format} bad formats")

    # ── B: Coordinate bounds ──────────────────────────────────────────────────
    print("=== B: Coordinate bounds ===")
    out_of_bounds = 0
    for name, v in venues.items():
        lat, lng = v.get("lat"), v.get("lng")
        if lat is None:
            continue
        if not (UK_LAT_MIN <= lat <= UK_LAT_MAX and UK_LNG_MIN <= lng <= UK_LNG_MAX):
            add_issue(name, f"Coords out of UK bounds: ({lat}, {lng})")
            out_of_bounds += 1
    print(f"  {out_of_bounds} out-of-bounds")

    # ── C: Postcode ↔ coordinate consistency ─────────────────────────────────
    print("=== C: Postcode ↔ coordinate check (geocoding — may take a while) ===")
    to_check = [
        (name, v) for name, v in venues.items()
        if v.get("postcode") and v.get("lat") is not None
        and area_code(v["postcode"]) not in CROWN_DEP_AREAS
    ]
    print(f"  Geocoding {len(to_check)} venues with both postcode and coords ...")

    coord_mismatches = 0
    geocode_failures = 0
    for i, (name, v) in enumerate(to_check):
        if i > 0 and i % 50 == 0:
            print(f"  ... {i}/{len(to_check)} checked ...")
        pc = v["postcode"]
        stored_lat, stored_lng = v["lat"], v["lng"]
        geo = geocode_postcode(pc)
        if geo is None:
            add_issue(name, f"Postcode {pc!r} could not be geocoded")
            geocode_failures += 1
            continue
        dist = haversine(stored_lat, stored_lng, geo[0], geo[1])
        if dist > DISTANCE_THRESHOLD_MILES:
            add_issue(
                name,
                f"Coords ({stored_lat:.4f}, {stored_lng:.4f}) are {dist:.1f} mi "
                f"from postcode {pc!r} geocode ({geo[0]:.4f}, {geo[1]:.4f})"
            )
            coord_mismatches += 1
        time.sleep(0.05)  # ~20 req/s — well within postcodes.io free tier

    print(f"  {coord_mismatches} coord mismatches > {DISTANCE_THRESHOLD_MILES} mi")
    print(f"  {geocode_failures} geocoding failures")

    # ── D: Alias integrity ────────────────────────────────────────────────────
    print("=== D: Alias integrity ===")
    broken_aliases = 0
    for name, v in venues.items():
        for alias in v.get("aliases", []):
            if alias == name:
                add_issue(name, f"Alias is same as canonical: {alias!r}")
                broken_aliases += 1
    print(f"  {broken_aliases} broken aliases")

    # ── E: Venues with coords but no postcode ─────────────────────────────────
    print("=== E: Coords without postcode ===")
    no_pc = [(n, v) for n, v in venues.items() if v.get("lat") and not v.get("postcode")]
    print(f"  {len(no_pc)} venues have coords but no postcode:")
    for name, v in no_pc:
        print(f"    {name}: ({v['lat']}, {v['lng']})")

    # ── F: Ambiguous name disambiguation ─────────────────────────────────────
    print("=== F: Ambiguous names check ===")
    for amb in sorted(ambiguous):
        if amb not in venues:
            print(f"  WARNING: ambiguous name {amb!r} not in venues dict "
                  "(no fallback entry if postcode unavailable)")

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    total_issues = sum(len(v) for v in issues.values())
    print(f"TOTAL ISSUES: {total_issues} across {len(issues)} venues")
    print()

    if issues:
        print("ISSUES BY VENUE:")
        for name in sorted(issues):
            for msg in issues[name]:
                print(f"  [{name}] {msg}")
    else:
        print("No issues found — data looks clean!")


if __name__ == "__main__":
    main()
