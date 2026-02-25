#!/usr/bin/env python3
"""Consolidate duplicate postcodes in venue_seeds.json.

Strategy:
1. Find all venues with the same postcode
2. Keep the longest/most complete name as canonical
3. Add shorter names as aliases
4. Remove duplicates
5. Report changes
"""

import json
from pathlib import Path
from collections import defaultdict

def main():
    seed_path = Path(__file__).parent.parent / "app" / "venue_seeds.json"

    print("Loading venue_seeds.json...")
    with open(seed_path) as f:
        data = json.load(f)

    venues = data["venues"]
    original_count = len(venues)

    # Group venues by postcode
    postcode_groups = defaultdict(list)
    for venue_name, venue_data in venues.items():
        postcode = venue_data.get("postcode")
        if postcode:
            postcode_groups[postcode].append(venue_name)

    # Find groups with duplicates
    duplicates = {pc: names for pc, names in postcode_groups.items() if len(names) > 1}
    print(f"\nFound {len(duplicates)} postcodes with duplicates")
    print(f"Affected venues: {sum(len(names) for names in duplicates.values())}")

    # Process each duplicate group
    consolidations = []
    venues_to_remove = set()

    for postcode, venue_names in sorted(duplicates.items()):
        # Sort by length (longest = most complete name)
        sorted_names = sorted(venue_names, key=len, reverse=True)
        canonical_name = sorted_names[0]
        alias_names = sorted_names[1:]

        print(f"\n{postcode}:")
        print(f"  Canonical: {canonical_name}")

        # Get existing aliases for canonical
        canonical_data = venues[canonical_name]
        existing_aliases = canonical_data.get("aliases", [])

        # Add new aliases
        for alias_name in alias_names:
            if alias_name not in existing_aliases:
                existing_aliases.append(alias_name)
                print(f"  Added alias: {alias_name}")
            else:
                print(f"  Already alias: {alias_name}")

            # Mark for removal
            venues_to_remove.add(alias_name)

        # Update canonical entry
        canonical_data["aliases"] = sorted(existing_aliases)

        consolidations.append({
            "postcode": postcode,
            "canonical": canonical_name,
            "aliases_added": alias_names,
        })

    # Remove duplicate entries
    print(f"\n\nRemoving {len(venues_to_remove)} duplicate entries...")
    for venue_name in venues_to_remove:
        del venues[venue_name]
        print(f"  Removed: {venue_name}")

    # Save updated data
    with open(seed_path, "w") as f:
        json.dump(data, f, indent=2)

    # Report
    print("\n" + "=" * 70)
    print("CONSOLIDATION COMPLETE")
    print("=" * 70)
    print(f"Original venues: {original_count}")
    print(f"Duplicate entries removed: {len(venues_to_remove)}")
    print(f"Final venue count: {len(venues)}")
    print(f"Net reduction: {original_count - len(venues)} venues")
    print(f"\nConsolidations: {len(consolidations)}")

    print("\n" + "=" * 70)
    print("CONSOLIDATION DETAILS")
    print("=" * 70)
    for cons in consolidations:
        print(f"\n{cons['postcode']}:")
        print(f"  Canonical: {cons['canonical']}")
        print(f"  Aliases: {', '.join(cons['aliases_added'])}")

    print(f"\n\nSeed file saved: {seed_path}")

if __name__ == "__main__":
    main()
