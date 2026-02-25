"""Tests for the venue seed data loader (app/seed_data.py)."""

from app.seed_data import get_ambiguous_names, get_venue_aliases, get_venue_seeds


def test_venue_seeds_loads():
    seeds = get_venue_seeds()
    assert isinstance(seeds, dict)
    assert len(seeds) > 500
    assert "Hickstead" in seeds
    assert seeds["Hickstead"]["postcode"] == "BN6 9NS"


def test_venue_seeds_coords():
    seeds = get_venue_seeds()
    hickstead = seeds["Hickstead"]
    assert abs(hickstead["lat"] - 50.962338) < 0.001
    assert abs(hickstead["lng"] - (-0.197713)) < 0.001


def test_venue_seeds_with_coords():
    """Venues with postcode should also have lat/lng after geocoding."""
    seeds = get_venue_seeds()
    dv = seeds["Dean Valley"]
    assert dv["postcode"] == "SK7 1RQ"
    assert "lat" in dv
    assert "lng" in dv


def test_aliases_derived():
    aliases = get_venue_aliases()
    assert isinstance(aliases, dict)
    assert len(aliases) > 200
    assert aliases["All England Show Jumping Course"] == "Hickstead"


def test_ambiguous_names():
    names = get_ambiguous_names()
    assert isinstance(names, set)
    assert "Rectory Farm" in names
    assert "Brook Farm" in names
    assert len(names) >= 14


def test_aliases_reference_known_venues():
    """Every alias target should be a key in the venues dict."""
    seeds = get_venue_seeds()
    aliases = get_venue_aliases()
    for alias, canonical in aliases.items():
        assert canonical in seeds, (
            f"Alias {alias!r} points to {canonical!r} which is not in venue seeds"
        )


def test_alias_only_venue():
    """Virtual venue 'Online' has aliases but no postcode."""
    seeds = get_venue_seeds()
    entry = seeds.get("Online")
    assert entry is not None
    assert entry.get("postcode") is None
    assert len(entry.get("aliases", [])) > 0
