#!/usr/bin/env python3
"""Phase 2: Web-crawl 517 venues to validate and find postcodes.

This script:
1. Loads the 517 venues with missing postcodes
2. Splits them into batches for parallel processing
3. Spawns Haiku agents to crawl each batch
4. Collects results and outputs only 100% validated venues
5. Identifies likely aliases/duplicates
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))


def split_venues_into_batches(venues: list[dict], batch_size: int = 20) -> list[list[dict]]:
    """Split venues into batches for parallel agent processing."""
    batches = []
    for i in range(0, len(venues), batch_size):
        batches.append(venues[i : i + batch_size])
    return batches


def generate_haiku_agent_prompt(venues: list[dict], batch_num: int, total_batches: int) -> str:
    """Generate prompt for a Haiku agent to crawl a batch of venues."""

    venues_json = json.dumps(venues, indent=2)

    return f"""You are a venue validator. Your task is to web-crawl the following {len(venues)} UK equestrian venues and validate them.

**CRITICAL RULES:**
1. ONLY return venues you are 100% CERTAIN are real with correct postcode
2. Use Google search, UK business directories, and venue websites
3. Verify postcode format: 2 letters/digits + digit/letter, space, digit + 2 letters (e.g., "SW1A 1AA")
4. If uncertain about postcode, return confidence < 1.0 (which means it won't be used)
5. Check if venue might be an alias of a famous/established venue
6. Ignore "Online" venues

**Venues to validate (Batch {batch_num}/{total_batches}):**
{venues_json}

**Return JSON with this structure for EACH venue:**
{{
  "venue_name": "Exact name from input",
  "postcode": "Valid UK postcode or null if not found",
  "website": "Official website URL if found",
  "confidence": 1.0,  // ONLY if 100% certain postcode is correct
  "notes": "Brief explanation of how postcode was verified",
  "is_likely_alias": false  // True if this appears to be alias of existing venue
}}

Return only an array of validated results. Skip any venues where confidence < 1.0.
Return empty array if no venues can be 100% validated.

Focus on finding postcodes by:
1. Searching "<venue_name> postcode UK"
2. Checking UK postcode lookup services
3. Finding official venue website contact/location pages
4. Cross-referencing with event listings that show postcodes
5. Checking business directories (Companies House, etc.)
"""


def main():
    """Main coordinator for Phase 2 web crawl."""
    from app.seed_data import get_venue_seeds

    # Load venues with missing postcodes
    manifest_path = Path(__file__).parent / "venues_missing_postcode.json"
    if not manifest_path.exists():
        print(f"Error: {manifest_path} not found")
        print("Run identify_new_venues.py first")
        sys.exit(1)

    with open(manifest_path) as f:
        venues = json.load(f)

    # Filter out "Online" venues
    venues = [v for v in venues if v["name"].lower() != "online"]
    print(f"Venues to validate: {len(venues)}")

    # Load seed data for alias checking
    seed_venues = get_venue_seeds()
    seed_names_lower = {name.lower() for name in seed_venues.keys()}
    print(f"Seed venues for dedup: {len(seed_names_lower)}")

    # Split into batches
    batches = split_venues_into_batches(venues, batch_size=20)
    print(f"Batches: {len(batches)}")

    # Print instructions for spawning agents
    print("\n" + "=" * 80)
    print("PHASE 2 WEB CRAWL — SPAWN PARALLEL HAIKU AGENTS")
    print("=" * 80)
    print(
        f"\nYou need to spawn {len(batches)} parallel Haiku agents."
        f"\nEach agent will crawl 20 venues and return only 100% validated results.\n"
    )

    for batch_num, batch in enumerate(batches, 1):
        prompt = generate_haiku_agent_prompt(batch, batch_num, len(batches))

        print(f"\n--- BATCH {batch_num}/{len(batches)} ---")
        print(f"Venues: {', '.join(v['name'][:30] for v in batch[:3])}...")
        print("\nPrompt length:", len(prompt), "chars")
        print(
            "\nTo run: Use Task tool with subagent_type='haiku'"
            f" (or claude-3-5-haiku if available)\n"
        )

    # Save batches for reference
    batches_path = Path(__file__).parent / "venue_crawl_batches.json"
    with open(batches_path, "w") as f:
        json.dump(
            {
                "total_venues": len(venues),
                "total_batches": len(batches),
                "batch_size": 20,
                "generated_at": datetime.now().isoformat(),
                "batches": [
                    {
                        "batch_num": i + 1,
                        "venues": batch,
                        "count": len(batch),
                    }
                    for i, batch in enumerate(batches)
                ],
            },
            f,
            indent=2,
        )

    print(f"\nBatch info saved to: {batches_path}")
    print("\n" + "=" * 80)
    print("NEXT STEPS:")
    print("=" * 80)
    print("1. Spawn Haiku agents to crawl each batch (see prompts above)")
    print("2. Collect validated results from each agent")
    print("3. Run phase3_process_crawl_results.py to update database")
    print("=" * 80)


if __name__ == "__main__":
    main()
