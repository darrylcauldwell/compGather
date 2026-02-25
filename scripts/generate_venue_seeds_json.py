#!/usr/bin/env python3
"""One-time script to generate app/venue_seeds.json from existing Python dicts.

Merges _VENUE_POSTCODE_SEEDS, _VENUE_ALIASES, and _AMBIGUOUS_VENUE_NAMES
into a single canonical JSON file. Delete this script after verification.

Uses ast.literal_eval to parse the dicts directly from source files,
avoiding full app imports that require all dependencies.
"""

import ast
import json
import re
import textwrap
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _extract_dict_or_set(source_path: Path, var_name: str) -> dict | set:
    """Extract a top-level dict or set literal from a Python source file."""
    source = source_path.read_text()

    # Find the assignment: "VAR_NAME = {" or "VAR_NAME: type = {"
    pattern = re.compile(
        rf"^{re.escape(var_name)}\s*(?::\s*[^=]+)?\s*=\s*",
        re.MULTILINE,
    )
    m = pattern.search(source)
    if not m:
        raise ValueError(f"Could not find {var_name} in {source_path}")

    # Find the opening brace
    start = source.index("{", m.start())

    # Track brace depth to find the matching close
    depth = 0
    i = start
    while i < len(source):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        elif ch in ('"', "'"):
            # Skip string literals (handle triple-quotes too)
            if source[i : i + 3] in ('"""', "'''"):
                quote = source[i : i + 3]
                i += 3
                while i < len(source) and source[i : i + 3] != quote:
                    i += 1
                i += 2  # skip closing triple-quote (loop adds 1 more)
            else:
                quote = ch
                i += 1
                while i < len(source) and source[i] != quote:
                    if source[i] == "\\":
                        i += 1
                    i += 1
        elif ch == "#":
            # Skip comments
            while i < len(source) and source[i] != "\n":
                i += 1
        i += 1

    literal = source[start : i + 1]
    return ast.literal_eval(literal)


def main() -> None:
    scanner_path = ROOT / "app" / "services" / "scanner.py"
    utils_path = ROOT / "app" / "parsers" / "utils.py"

    # 1. Parse the dicts from source
    seeds = _extract_dict_or_set(scanner_path, "_VENUE_POSTCODE_SEEDS")
    aliases = _extract_dict_or_set(utils_path, "_VENUE_ALIASES")
    ambiguous = _extract_dict_or_set(utils_path, "_AMBIGUOUS_VENUE_NAMES")

    # 2. Build {canonical_name: {postcode?, lat?, lng?, aliases?}} from seeds
    venues: dict[str, dict] = {}

    for name, value in seeds.items():
        entry: dict = {}
        if isinstance(value, tuple):
            postcode, lat, lng = value
            entry["postcode"] = postcode
            entry["lat"] = lat
            entry["lng"] = lng
        else:
            entry["postcode"] = value
        venues[name] = entry

    # 3. Invert aliases: group by canonical name
    alias_groups: dict[str, list[str]] = defaultdict(list)
    for alias_name, canonical_name in aliases.items():
        alias_groups[canonical_name].append(alias_name)

    # 4. Merge aliases into venues dict
    for canonical_name, alias_list in alias_groups.items():
        if canonical_name not in venues:
            venues[canonical_name] = {}
        venues[canonical_name]["aliases"] = sorted(alias_list)

    # 5. Sort venues by name for clean diffs
    sorted_venues = dict(sorted(venues.items(), key=lambda x: x[0].lower()))

    # 6. Build output
    output = {
        "venues": sorted_venues,
        "ambiguous_names": sorted(ambiguous),
    }

    # 7. Write JSON
    out_path = ROOT / "app" / "venue_seeds.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # 8. Report
    total_venues = len(sorted_venues)
    with_postcode = sum(1 for v in sorted_venues.values() if "postcode" in v)
    with_coords = sum(1 for v in sorted_venues.values() if "lat" in v)
    with_aliases = sum(1 for v in sorted_venues.values() if "aliases" in v)
    total_aliases = sum(len(v.get("aliases", [])) for v in sorted_venues.values())
    ambiguous_count = len(output["ambiguous_names"])

    print(f"Written to {out_path}")
    print(f"  Venues: {total_venues}")
    print(f"  With postcode: {with_postcode}")
    print(f"  With coords: {with_coords}")
    print(f"  With aliases: {with_aliases} venues ({total_aliases} alias entries)")
    print(f"  Ambiguous names: {ambiguous_count}")


if __name__ == "__main__":
    main()
