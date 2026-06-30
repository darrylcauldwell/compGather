#!/usr/bin/env python3
"""One-off backfill: populate competitions.description and re-extract tags from
the stored raw_extract.

Every event is stored with `raw_extract` = the full ExtractedEvent JSON, which
already includes the parser's class list and any description — text we never fed
into tagging (tags were derived from the name only). This recovers it WITHOUT
re-scraping: for each row it sets the description column (blurb, else a class
summary) and re-runs extract_tags over name + description + classes, so series/
affiliation signals that live in class names (NSEA, Pony Club, BSPS, and later
series: tags) are picked up retroactively.

Run inside the container (after the description-column migration):
    docker exec equicalendar python scripts/backfill_event_text.py
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.scanner import _SOURCE_DEFS  # noqa: E402
from app.services.tag_manager import extract_tags, serialize_tags  # noqa: E402

DB_PATH = Path("data/equicalendar.db")


def _affiliation_by_parser_key() -> dict[str, str | None]:
    return {d["parser_key"]: d.get("affiliation") for d in _SOURCE_DEFS if d.get("parser_key")}


def main() -> None:
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    aff_map = _affiliation_by_parser_key()
    parser_key_by_source = {
        r["id"]: r["parser_key"] for r in conn.execute("SELECT id, parser_key FROM sources")
    }

    rows = conn.execute(
        "SELECT id, source_id, name, discipline, event_type, tags, description, classes, raw_extract "
        "FROM competitions"
    ).fetchall()

    scanned = desc_set = classes_set = tags_changed = 0
    for r in rows:
        if not r["raw_extract"]:
            continue
        try:
            raw = json.loads(r["raw_extract"])
        except (json.JSONDecodeError, TypeError):
            continue
        scanned += 1

        classes = raw.get("classes") or []
        blurb = raw.get("description") or None
        detail_text = " ".join(filter(None, [blurb, " ".join(classes)])).strip()
        new_desc = blurb
        new_classes = json.dumps(classes) if classes else None

        source_aff = aff_map.get(parser_key_by_source.get(r["source_id"]))
        tags = extract_tags(
            name=r["name"] or "",
            description=detail_text,
            discipline=r["discipline"],
            event_type=r["event_type"] or "competition",
            source_affiliation=source_aff,
            classes=classes,
        )
        new_tags = serialize_tags(tags) if tags else None

        updates: list[tuple[str, object]] = []
        if new_desc != r["description"]:
            updates.append(("description", new_desc))
        if new_classes != r["classes"]:
            updates.append(("classes", new_classes))
        if new_tags != r["tags"]:
            updates.append(("tags", new_tags))
        if updates:
            assignments = ", ".join(f"{col} = ?" for col, _ in updates)
            conn.execute(
                f"UPDATE competitions SET {assignments} WHERE id = ?",
                [val for _, val in updates] + [r["id"]],
            )
            desc_set += any(col == "description" for col, _ in updates)
            classes_set += any(col == "classes" for col, _ in updates)
            tags_changed += any(col == "tags" for col, _ in updates)

    conn.commit()
    conn.close()
    print(
        f"backfill: {scanned} rows with raw_extract scanned, "
        f"{desc_set} descriptions set, {classes_set} class-lists set, "
        f"{tags_changed} tag-sets updated"
    )


if __name__ == "__main__":
    main()
