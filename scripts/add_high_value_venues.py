#!/usr/bin/env python3
"""Add 36 high-value web-validated venues to venue_seeds.json."""

import json
from pathlib import Path
from datetime import datetime

def main():
    seed_path = Path(__file__).parent.parent / "app" / "venue_seeds.json"

    # 36 newly validated high-value venues
    new_venues = [
        ("West Park Equestrian Services", "DL13 4NR"),
        ("Prestige Equestrian Llp", "GL2 2RG"),
        ("Scottish National Equestrian Centre", "EH52 6NH"),
        ("Lower Stocklands Farm", "CF5 6DR"),
        ("Dorset Polo Club", "BH16 6HQ"),
        ("Billow Farm", "GL13 9HF"),
        ("Berwick Farm, Ongar", "CM5 9PY"),
        ("Knapp Farm", "HR3 6JD"),
        ("Dressage At Hascombe", "BN5 9SA"),
        ("Bryn Derw Farm", "LL55 3PD"),
        ("Cheston Farm Equestrian Centre", "TQ10 9HL"),
        ("Eldwick Riding Club", "BD16 3EU"),
        ("Riseholme Equestrian College", "LN1 2ZR"),
        ("Equitex Arena", "LU6 2NW"),
        ("Garlidna Farm", "TR13 0JX"),
        ("Porth Valley Equestrian", "TR8 4JL"),
        ("Oxstalls", "GL6 8HZ"),
        ("Bullions Farm", "DH8 9LS"),
        ("Stretcholt Farm", "TA6 4SR"),
        ("The Talland School Of Equitation", "GL7 5FD"),
        ("Braishfield Manor", "SO51 0PS"),
        ("Hammer And Harp Farm", "SL2 3XJ"),
        ("Rosevidney Farm", "TR20 9BX"),
        ("Geldeston Hall", "NR34 0LP"),
        ("Blackdyke Farm", "CA6 4EY"),
        ("The Cabin", "AB51 0LL"),
        ("The Unicorn Equestrian Centre", "GL54 1JZ"),
        ("Amberley Court", "HR1 3BX"),
        ("Turndale Stables", "ST10 4HS"),
        ("Home Farm Arena Alconbury", "PE28 4DN"),
        ("Addington Manor E C Limited", "MK18 2JR"),
        ("Foresterseat Cross Country", "PH2 9QF"),
        ("Glebe Farm", "NN29 7LB"),
        ("Rectory Farm", "GL7 7JW"),
        ("The Playbarn", "NR14 7LP"),
    ]

    print(f"Loading venue_seeds.json...")
    with open(seed_path) as f:
        seeds = json.load(f)

    existing_venues = seeds["venues"]
    print(f"Current venues in seed data: {len(existing_venues)}")

    added = 0
    skipped = 0
    skipped_list = []

    for venue_name, postcode in new_venues:
        # Check if already exists (case-insensitive)
        exists = any(
            v.lower() == venue_name.lower()
            for v in existing_venues.keys()
        )

        if exists:
            skipped += 1
            skipped_list.append(venue_name)
            continue

        # Add new venue
        existing_venues[venue_name] = {
            "postcode": postcode,
            "aliases": []
        }
        added += 1

    # Save
    with open(seed_path, "w") as f:
        json.dump(seeds, f, indent=2)

    print(f"\n✅ High-value venues added!")
    print(f"   Added: {added} venues")
    print(f"   Skipped (already exist): {skipped} venues")
    print(f"   Total venues now: {len(existing_venues)}")

    if skipped_list:
        print(f"\nAlready in seed data:")
        for name in skipped_list:
            print(f"   - {name}")

    print(f"\nSeed file updated: {seed_path}")
    print(f"Total progress: 77 (first batch) + {added} (high-value) = {77 + added} venues added")

if __name__ == "__main__":
    main()
