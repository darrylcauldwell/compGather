#!/usr/bin/env python3
"""
Find all postcodes in the database with 2+ venues.
Report groups for manual review and consolidation approval.
"""

import sqlite3
import json
from pathlib import Path
from collections import defaultdict

# Database path
db_path = Path(__file__).parent.parent / "compGather.db"

def find_duplicate_postcodes():
    """Query database for postcodes with multiple venues."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Find all postcodes that appear on 2+ venues
    cursor.execute("""
        SELECT postcode, COUNT(*) as venue_count
        FROM venues
        WHERE postcode IS NOT NULL
        GROUP BY postcode
        HAVING COUNT(*) >= 2
        ORDER BY venue_count DESC, postcode ASC
    """)

    postcode_groups = cursor.fetchall()

    # For each duplicate postcode, get all venues
    duplicate_postcodes = {}
    for row in postcode_groups:
        postcode = row['postcode']
        count = row['venue_count']

        cursor.execute("""
            SELECT id, name, source, seed_batch, validation_source, confidence
            FROM venues
            WHERE postcode = ?
            ORDER BY name ASC
        """, (postcode,))

        venues = [dict(v) for v in cursor.fetchall()]

        duplicate_postcodes[postcode] = {
            'count': count,
            'venues': venues
        }

    conn.close()
    return duplicate_postcodes


def format_report(duplicate_postcodes):
    """Format duplicate postcodes for display."""
    if not duplicate_postcodes:
        return "No duplicate postcodes found."

    lines = []
    lines.append("=" * 150)
    lines.append(f"PHASE 1 & 2: DUPLICATE POSTCODES IN DATABASE")
    lines.append(f"Total postcode groups: {len(duplicate_postcodes)}")
    lines.append("=" * 150)
    lines.append("")

    for postcode in sorted(duplicate_postcodes.keys()):
        group = duplicate_postcodes[postcode]
        count = group['count']
        venues = group['venues']

        lines.append(f"Postcode: {postcode} ({count} venues)")
        lines.append("-" * 150)

        for v in venues:
            source_tag = f"[{v['source']}]" if v['source'] else ""
            batch_tag = f"({v['seed_batch']})" if v['seed_batch'] else ""
            confidence_tag = f"conf={v['confidence']}" if v['confidence'] else "unvalidated"

            tags = " ".join(filter(None, [source_tag, batch_tag, confidence_tag]))

            lines.append(f"  ID {v['id']:4} | {v['name']:80} {tags}")

        lines.append("")

    return "\n".join(lines)


def generate_json_report(duplicate_postcodes):
    """Generate JSON report for programmatic use."""
    report = {
        "total_postcode_groups": len(duplicate_postcodes),
        "postcode_groups": {}
    }

    for postcode in sorted(duplicate_postcodes.keys()):
        group = duplicate_postcodes[postcode]
        report["postcode_groups"][postcode] = {
            "count": group['count'],
            "venues": group['venues']
        }

    return report


if __name__ == "__main__":
    print("Scanning database for duplicate postcodes...")
    duplicates = find_duplicate_postcodes()

    # Display formatted report
    report_text = format_report(duplicates)
    print(report_text)

    # Save JSON report to /tmp for reference
    json_report = generate_json_report(duplicates)
    with open("/tmp/duplicate_postcodes_report.json", "w") as f:
        json.dump(json_report, f, indent=2)

    print(f"\n✓ JSON report saved to /tmp/duplicate_postcodes_report.json")
    print(f"✓ Total duplicate postcode groups: {len(duplicates)}")
