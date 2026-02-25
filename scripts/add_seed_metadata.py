#!/usr/bin/env python3
"""Add source metadata to newly added venues in venue_seeds.json.

Marks 98 web-crawled venues with:
- source: "seed_data"
- seed_batch: batch identifier
- validation_source: how it was validated
- confidence: 1.0 (100% validated)
"""

import json
from pathlib import Path
from datetime import datetime

def main():
    seed_path = Path(__file__).parent.parent / "app" / "venue_seeds.json"

    # Venues from first batch (web-crawl validation)
    batch_1_venues = [
        ("Speedgate Events", "batch_1_web_crawl", "website"),
        ("Field Farm Cross Country", "batch_1_web_crawl", "website"),
        ("Fox Farm", "batch_1_web_crawl", "company_house"),
        ("Bury Farm", "batch_1_web_crawl", "website"),
        ("Ian Stark", "batch_1_web_crawl", "website"),
        ("Port Royal Equestrian & Exhibition Centre", "batch_1_web_crawl", "website"),
        ("Hartpury University And Hartpury College", "batch_1_web_crawl", "website"),
        ("Brook Farm", "batch_1_web_crawl", "website"),
        ("Aster Academy Dressage", "batch_1_web_crawl", "company_house"),
        ("Oak Lodge", "batch_1_web_crawl", "bhs_listing"),
        ("The Windmill", "batch_1_web_crawl", "website"),
        ("Jlb Stables", "batch_1_web_crawl", "business_dir"),
        ("Cannington", "batch_1_web_crawl", "college_website"),
        ("Waverton House", "batch_1_web_crawl", "website"),
        ("Cockshot", "batch_1_web_crawl", "event_listing"),
        ("The Cabin Equestrian Riding Club", "batch_1_web_crawl", "website"),
        ("Moor Farm", "batch_1_web_crawl", "website"),
        ("Hill Farm", "batch_1_web_crawl", "website"),
    ]

    # Venues from high-value batch (top venues by competition count)
    batch_2_venues = [
        ("Little Limber Grange", "batch_2_high_value", "postcode_dir"),
        ("Diamond Hall Farm", "batch_2_high_value", "event_listing"),
        ("Dairy Farm", "batch_2_high_value", "website"),
        ("Lime Kiln Farm", "batch_2_high_value", "website"),
        ("Sunnybank Farm", "batch_2_high_value", "website"),
        ("Breach Barn", "batch_2_high_value", "business_dir"),
        ("Greenlands", "batch_2_high_value", "website"),
        ("Boomerang Stables", "batch_2_high_value", "website"),
        ("Dorset Polo Club", "batch_2_high_value", "website"),
        ("Billow Farm", "batch_2_high_value", "business_dir"),
        ("Braishfield Manor", "batch_2_high_value", "event_listing"),
        ("Hammer And Harp Farm", "batch_2_high_value", "event_listing"),
        ("Rosevidney Farm", "batch_2_high_value", "website"),
        ("Amberley Court", "batch_2_high_value", "website"),
        ("Turndale Stables", "batch_2_high_value", "venue_dir"),
        ("Home Farm Arena Alconbury", "batch_2_high_value", "website"),
        ("Addington Manor E C Limited", "batch_2_high_value", "company_house"),
        ("Foresterseat Cross Country", "batch_2_high_value", "website"),
        ("Glebe Farm", "batch_2_high_value", "website"),
        ("Rectory Farm", "batch_2_high_value", "website"),
        ("The Playbarn", "batch_2_high_value", "website"),
    ]

    all_venues = batch_1_venues + batch_2_venues

    print(f"Loading venue_seeds.json...")
    with open(seed_path) as f:
        data = json.load(f)

    venues = data["venues"]
    updated = 0
    not_found = 0

    print(f"\nAdding metadata to {len(all_venues)} newly added venues...")

    for venue_name, batch_id, validation_source in all_venues:
        if venue_name in venues:
            venues[venue_name]["source"] = "seed_data"
            venues[venue_name]["seed_batch"] = batch_id
            venues[venue_name]["validation_source"] = validation_source
            venues[venue_name]["confidence"] = 1.0
            updated += 1
        else:
            print(f"  ⚠️  Not found: {venue_name}")
            not_found += 1

    # Save updated data
    with open(seed_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\n✅ Metadata updated!")
    print(f"   Updated: {updated} venues")
    print(f"   Not found: {not_found} venues")
    print(f"   Total venues: {len(venues)}")
    print(f"\nSeed file saved: {seed_path}")

if __name__ == "__main__":
    main()
