"""Thin loader for venue seed data from venue_seeds.json.

All venue seed data (postcodes, coordinates, aliases, ambiguous names)
lives in app/venue_seeds.json — the single source of truth.
This module provides typed accessors with lazy-load + module-level cache.
"""

from __future__ import annotations

import json
from pathlib import Path

_DATA: dict | None = None


def _load() -> dict:
    global _DATA
    if _DATA is None:
        path = Path(__file__).with_name("venue_seeds.json")
        with open(path) as f:
            _DATA = json.load(f)
    return _DATA


def get_venue_seeds() -> dict[str, dict]:
    """Return {canonical_name: {postcode?, lat?, lng?, aliases?}}."""
    return _load()["venues"]


def get_venue_aliases() -> dict[str, str]:
    """Return {alias_name: canonical_name} derived from nested aliases."""
    aliases: dict[str, str] = {}
    for canonical, data in _load()["venues"].items():
        for alias in data.get("aliases", []):
            aliases[alias] = canonical
    return aliases


def get_ambiguous_names() -> set[str]:
    """Return set of generic names needing postcode disambiguation."""
    return set(_load()["ambiguous_names"])


def get_discipline_seeds() -> dict[str, dict]:
    """Return {discipline_name: {aliases?, is_competition?, description?}}."""
    return _load().get("disciplines", {})


def get_discipline_aliases() -> dict[str, str]:
    """Return {alias: canonical_discipline} derived from nested aliases."""
    aliases: dict[str, str] = {}
    for canonical, data in get_discipline_seeds().items():
        for alias in data.get("aliases", []):
            aliases[alias.lower()] = canonical
    return aliases


def get_tag_keywords() -> dict[str, list[str]]:
    """Return {tag: [keywords]} for event type classification.

    Example: {"type:training": ["training", "clinic", "workshop"], ...}
    """
    return _load().get("tag_keywords", {})
