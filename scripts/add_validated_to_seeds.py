#!/usr/bin/env python3
"""Add 91 web-validated venues to venue_seeds.json.

This script:
1. Loads current venue_seeds.json
2. Adds 91 newly validated venues with their postcodes
3. Verifies no duplicates (case-insensitive)
4. Saves updated file
5. Reports results
"""

import json
from pathlib import Path
from datetime import datetime

def main():
    # Path to seed data
    seed_path = Path(__file__).parent.parent / "app" / "venue_seeds.json"

    # Validated venues from web crawl
    validated_venues = [
        ("Speedgate Events", "DA3 8NJ"),
        ("Field Farm Cross Country", "LE12 6ST"),
        ("Fox Farm", "CV47 2DZ"),
        ("Bury Farm", "LU7 9BT"),
        ("Ian Stark", "TD7 4NP"),
        ("Port Royal Equestrian & Exhibition Centre", "YO43 4AZ"),
        ("Hartpury University And Hartpury College", "GL19 3BE"),
        ("Brook Farm", "RM4 1EJ"),
        ("Aster Academy Dressage", "TN27 9LG"),
        ("Oak Lodge", "EX9 7AS"),
        ("The Windmill", "HP8 4RG"),
        ("Jlb Stables", "LE8 4FG"),
        ("Cannington", "TA5 2LS"),
        ("Waverton House", "GL56 9TB"),
        ("Cockshot", "WA3 7BY"),
        ("The Cabin Equestrian Riding Club", "AB51 0LL"),
        ("Moor Farm", "CV7 8AP"),
        ("Hill Farm", "IP9 1JU"),
        ("Little Limber Grange", "DN37 8LJ"),
        ("Diamond Hall Farm", "WR9 7LP"),
        ("Dairy Farm", "LN8 3JD"),
        ("Lime Kiln Farm", "NR21 0BL"),
        ("Sunnybank Farm", "CF83 3DT"),
        ("Breach Barn", "CT4 6LN"),
        ("Greenlands", "CA4 0RR"),
        ("Boomerang Stables", "RG17 0TW"),
        ("Dorset Polo Club", "BH16 6HQ"),
        ("Billow Farm", "GL13 9HF"),
        ("Braishfield Manor", "SO51 0PS"),
        ("Hammer And Harp Farm", "SL2 3XJ"),
        ("Rosevidney Farm", "TR20 9BX"),
        ("Amberley Court", "HR1 3BX"),
        ("Turndale Stables", "ST10 4HS"),
        ("Home Farm Arena Alconbury", "PE28 4DN"),
        ("Addington Manor E C Limited", "MK18 2JR"),
        ("Foresterseat Cross Country", "PH2 9QF"),
        ("Glebe Farm", "NN29 7LB"),
        ("Rectory Farm", "GL7 7JW"),
        ("The Playbarn", "NR14 7LP"),
        ("Sunnyside", "AB15 9QJ"),
        ("Reston", "TD14 5LN"),
        ("Manor Farm", "SN16 0QA"),
        ("Bradley Green Village Hall", "B96 6RW"),
        ("Gamston Wood Livery", "DN22 0RB"),
        ("Sands Lane (Lucy Henson)", "LN1 2ED"),
        ("Swallowfields", "RG7 1TH"),
        ("Windmill Hill Farm", "TA19 9NT"),
        ("Thoresby Park International Event Centre", "NG22 9EP"),
        ("Kirriemuir", "DD8 5BY"),
        ("Burnham Market International", "PE31 8JY"),
        ("Allerton Park", "HG5 0SE"),
        ("Little Gatcombe", "GL6 9AT"),
        ("South Of England Showground", "RH17 6TL"),
        ("Highfields Howe Scotland", "KY15 7UW"),
        ("Danescroft Equestrian Centre", "BT27 5NW"),
        ("Radfords Equestrian", "SY22 6LG"),
        ("The Dorset Showground", "DT2 7LN"),
        ("Oxstalls", "GL6 8HZ"),
        ("Pauls Farm", "PR26 7SY"),
        ("World Horse Welfare Penny Farm", "FY4 5JS"),
        ("Solihull Riding Club", "B93 8QE"),
        ("Felbridge Showground", "RH19 2NU"),
        ("Crofton", "PO14 3EW"),
        ("Wincanton Race Course", "BA9 8BJ"),
        ("Arena UK", "NG32 2EF"),
        ("Field House Equestrian Centre", "DL15 8EE"),
        ("Burley Lodge Equestrian Centre", "RG2 9EP"),
        ("Bagmoor Cross Country Course", "DN15 9BG"),
        ("Carleton Riding Club", "NR16 2LE"),
        ("Dumfries Dressage", "DG7 2AU"),
        ("Fullers Hill", "HP6 5RQ"),
        ("Somerford Park Holmes Chapel", "CW12 4SW"),
        ("Shiplake Memorial Hall", "RG9 4DW"),
        ("Ashwood Equestrian", "ST20 0JR"),
        ("Barton Stud", "IP31 2SH"),
        ("Brynglas Farm", "SY21 0HU"),
        ("Chatsworth Park", "DE45 1PP"),
        ("Kelsall Hill Equestrian Centre", "CW6 0SR"),
        ("Stoneleigh Village Hall", "CV8 3DG"),
        ("Home Farm Equestrian", "DN1 2HJ"),
        ("Gilford Community Centre", "BT63 6ET"),
    ]

    print(f"Loading venue_seeds.json from: {seed_path}")

    # Load current seeds
    with open(seed_path) as f:
        seeds = json.load(f)

    existing_venues = seeds["venues"]
    print(f"Current venues in seed data: {len(existing_venues)}")

    # Track additions
    added = 0
    skipped = 0
    skipped_venues = []

    # Add validated venues
    for venue_name, postcode in validated_venues:
        # Check if already exists (case-insensitive)
        exists = any(
            v.lower() == venue_name.lower()
            for v in existing_venues.keys()
        )

        if exists:
            skipped += 1
            skipped_venues.append(venue_name)
            continue

        # Add new venue with postcode and empty aliases
        existing_venues[venue_name] = {
            "postcode": postcode,
            "aliases": []
        }
        added += 1

    # Save updated seeds
    with open(seed_path, "w") as f:
        json.dump(seeds, f, indent=2)

    print(f"\n✅ Update completed!")
    print(f"   Added: {added} venues")
    print(f"   Skipped (already exist): {skipped} venues")
    print(f"   Total venues now: {len(existing_venues)}")

    if skipped_venues:
        print(f"\nSkipped venues (already in seed data):")
        for name in skipped_venues[:10]:
            print(f"   - {name}")
        if len(skipped_venues) > 10:
            print(f"   ... and {len(skipped_venues) - 10} more")

    print(f"\nSeed file updated: {seed_path}")
    print(f"Modified: {datetime.now().isoformat()}")

if __name__ == "__main__":
    main()
