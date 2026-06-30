#!/usr/bin/env python3
"""One-off cleanup: hide existing camp/clinic booking-payment listings.

Sources like Horse Events list each instalment of a Pony Club camp as a separate
row ("DEPOSIT", "1st payment", "Final instalment"), exploding one camp into many
rows that aren't events to browse. The scanner now hides these on ingest
(`_BOOKING_PAYMENT_RE` in app/services/scanner.py); this script applies the same
rule to rows already in the database.

Reversible: it only flips `hidden`. To undo, set `hidden = 0` for the same rows.

Runs inside the Docker container:
    docker exec equicalendar python scripts/hide_booking_payments.py          # dry-run
    docker exec equicalendar python scripts/hide_booking_payments.py --apply   # apply
"""

import sqlite3
import sys
from pathlib import Path

# Allow importing the shared regex so cleanup and ingest stay in lockstep.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.scanner import _BOOKING_PAYMENT_RE  # noqa: E402

DB_PATH = Path("data/equicalendar.db")


def main() -> None:
    apply = "--apply" in sys.argv[1:]
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    # Filter in Python with the same regex the scanner uses (SQLite has no regexp
    # by default), so we hide exactly what ingest would now hide.
    cur.execute("SELECT id, name FROM competitions WHERE hidden IS NOT 1")
    to_hide = [(cid, name) for cid, name in cur.fetchall() if _BOOKING_PAYMENT_RE.search(name or "")]

    print(f"{len(to_hide)} visible booking-payment rows to hide:")
    for _, name in to_hide[:20]:
        print(f"    {name[:70]}")
    if len(to_hide) > 20:
        print(f"    ... and {len(to_hide) - 20} more")

    if not apply:
        print("\nDry-run. Re-run with --apply to hide these rows.")
        conn.close()
        return

    cur.executemany(
        "UPDATE competitions SET hidden = 1 WHERE id = ?",
        [(cid,) for cid, _ in to_hide],
    )
    conn.commit()
    print(f"\nHid {len(to_hide)} rows.")
    conn.close()


if __name__ == "__main__":
    main()
