#!/usr/bin/env python3
"""Validate which itsplainsailing.com Pony Club branch URLs are active.

This script quickly checks all 93 configured club URLs to see which ones:
1. Return a valid HTTP response
2. Contain event container elements

Usage:
    python scripts/validate_itsplainsailing_clubs.py

Output:
    - Prints list of working/dead clubs
    - Updates ITS_PLAIN_SAILING_CLUBS in app/parsers/its_plain_sailing.py with only working clubs
    - Can be used to filter before running full parser scan
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# All 93 Irish Pony Club branches on itsplainsailing.com
ALL_CLUBS = [
    # Area 1: Wicklow/Carlow (11)
    "brayhunt", "carlowhunt", "cherryorchard", "shillelagh", "wicklowhunt", "rathfarnham",
    "farnham", "naul", "northcounty", "coolfin", "coolfin2",
    # Area 2: Kildare/Laois/Offaly/Meath (12)
    "calliaghstown", "laois", "kildarehunt", "newcastelyons", "offaly", "southwestmeath",
    "kildare", "naas", "nmeath", "balrath", "balrath2", "meathfox",
    # Area 3: Kilkenny/Tipperary/Waterford (9)
    "goldenvale", "northkilkenny", "tipperaryhunt", "waterfordhunt", "westwaterford",
    "birdhill", "corkhunt", "duhallow2", "limerickhunt",
    # Area 4: Wexford/Carlow (10)
    "islandhunt", "kilkennyhunt", "killinick", "warrington", "wexfordhunt",
    "wexford", "southkilkenny", "tackern", "tackern2", "tackern3",
    # Area 5: Cork (11)
    "araglen", "avondhu", "beara", "carberyhunt", "duhallow", "muskerry", "southunion",
    "unitedhunt", "glanmire", "imokilly", "youghal",
    # Area 6: Donegal/Leitrim/Longford/Sligo (10)
    "clewbay", "eastdonegal", "longford", "moyvalley", "sligohunt",
    "leitrim", "northlongford", "roscommon", "southroscommon", "tulsk",
    # Area 7: Cavan/Louth/Meath/Monaghan (10)
    "cavan", "louthhunt", "meathhunt", "monaghan", "wardunion",
    "dundalk", "ferbane", "granard", "oldmeath", "tyrrellspass",
    # Area 8: Galway (10)
    "ballyjennings", "eastgalway", "galwaymid", "galwayhunt", "tuam", "tynagh",
    "claremorris", "glinsk", "glinsk2", "portumna",
    # Area 9: Clare/Limerick/Tipperary (10)
    "clare", "limerick", "northtipperary", "scarteen", "kingdom", "nenagh", "thomond",
    "eastclare", "westclare", "ormond",
    # Northern Ireland clubs (10)
    "northdown", "eastantrim", "eastdown", "seskinore", "tpc", "iveaghpc",
    "killultagh", "midantrim", "bushmills", "clogher",
]


async def check_club_url(client: httpx.AsyncClient, club_slug: str) -> tuple[str, bool, str]:
    """Check if a club URL is valid and has event content.

    Returns:
        (club_slug, is_working, status_message)
    """
    url = f"https://itsplainsailing.com/org/{club_slug}"

    try:
        # Quick HTTP check with short timeout
        resp = await client.get(url, timeout=10.0, follow_redirects=True)

        # Check for valid HTTP response
        if resp.status_code not in (200, 301, 302, 304):
            return (club_slug, False, f"HTTP {resp.status_code}")

        # Check if response contains event-related HTML elements
        soup = BeautifulSoup(resp.text, "html.parser")

        # Look for common event container patterns
        has_events = bool(
            soup.select("div[class*='event']") or
            soup.select("div[class*='card']") or
            soup.select("div[data-event-id]") or
            soup.select("article") or
            soup.find(string=lambda s: s and any(
                x in s.lower() for x in ["event", "competition", "rally", "camp", "2026", "2025"]
            ))
        )

        if has_events:
            return (club_slug, True, "OK")
        else:
            return (club_slug, False, "No event elements found")

    except asyncio.TimeoutError:
        return (club_slug, False, "Timeout")
    except Exception as e:
        return (club_slug, False, f"Error: {str(e)[:50]}")


async def validate_all_clubs() -> tuple[list[str], list[tuple[str, str]]]:
    """Validate all clubs and return working and dead club lists."""
    working = []
    dead = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Check in batches of 10 for progress feedback
        batch_size = 10
        for i in range(0, len(ALL_CLUBS), batch_size):
            batch = ALL_CLUBS[i : i + batch_size]
            results = await asyncio.gather(
                *[check_club_url(client, slug) for slug in batch],
                return_exceptions=False,
            )

            for club_slug, is_working, status in results:
                status_icon = "✓" if is_working else "✗"
                logger.info(f"  {status_icon} {club_slug:20} — {status}")

                if is_working:
                    working.append(club_slug)
                else:
                    dead.append((club_slug, status))

            logger.info(f"  Progress: {i + len(batch)}/{len(ALL_CLUBS)}\n")

            # Rate limiting between batches
            await asyncio.sleep(0.5)

    return working, dead


def update_parser_file(working_clubs: list[str]) -> None:
    """Update the parser file with only working club slugs."""
    parser_file = Path(__file__).parent.parent / "app" / "parsers" / "its_plain_sailing.py"

    with open(parser_file, "r") as f:
        content = f.read()

    # Find the ITS_PLAIN_SAILING_CLUBS definition and replace it
    # We'll replace from the opening bracket to the closing bracket
    import re

    pattern = r"ITS_PLAIN_SAILING_CLUBS = \[(.*?)\n\]"
    replacement = f"""ITS_PLAIN_SAILING_CLUBS = [
    {', '.join(repr(c) for c in working_clubs)}
]"""

    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    if new_content != content:
        with open(parser_file, "w") as f:
            f.write(new_content)
        logger.info(f"\n✓ Updated {parser_file} with {len(working_clubs)} working clubs")
    else:
        logger.warning(f"\n✗ Could not update parser file (pattern not found)")


async def main() -> None:
    logger.info(f"Validating {len(ALL_CLUBS)} itsplainsailing.com club URLs...\n")

    working, dead = await validate_all_clubs()

    logger.info("\n" + "=" * 60)
    logger.info(f"RESULTS: {len(working)} working, {len(dead)} dead out of {len(ALL_CLUBS)} total")
    logger.info("=" * 60)

    if working:
        logger.info(f"\n✓ WORKING CLUBS ({len(working)}):")
        for slug in working:
            logger.info(f"  • {slug}")

    if dead:
        logger.info(f"\n✗ DEAD CLUBS ({len(dead)}):")
        for slug, reason in dead:
            logger.info(f"  • {slug:20} — {reason}")

    # Ask to update parser
    if working:
        response = input(
            f"\nUpdate parser with {len(working)} working clubs? (y/n): "
        ).strip().lower()
        if response == "y":
            update_parser_file(working)
            logger.info("\n✓ Parser updated! Run scans with only active clubs.")
        else:
            logger.info("\nParser not updated. Working clubs list above can be used manually.")


if __name__ == "__main__":
    asyncio.run(main())
