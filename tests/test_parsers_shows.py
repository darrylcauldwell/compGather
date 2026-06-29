"""Contract tests for the data-driven static show fixtures.

The ~80 former per-show stub parsers (which fetched a URL, discarded the
response, and returned hard-coded constants) were consolidated into a single
:class:`StaticShowParser` backed by ``app/parsers/static_shows.json``.

These tests assert the *contract* of that data + parser rather than restating
each show's hard-coded constants (which the old tests did — tautological and
time-bombed). They verify: every seed key registers and resolves correctly,
every event is well-formed, the parser performs no network I/O, the source URL
is injected, and ``valid_until`` is derived correctly.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
import pytest

from app.parsers.registry import get_parser
from app.parsers.static_show import StaticShowParser, get_static_shows

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ALLOWED_EVENT_TYPES = {None, "competition", "show", "training"}

SHOWS = get_static_shows()
KEYS = sorted(SHOWS)
# (key, index, event) for per-event parametrisation with readable ids
EVENTS = [
    (key, i, ev)
    for key in KEYS
    for i, ev in enumerate(SHOWS[key]["events"])
]


def test_seed_is_non_empty():
    assert len(KEYS) > 50, "expected the full static-show catalogue"
    assert sum(len(SHOWS[k]["events"]) for k in KEYS) >= len(KEYS)


@pytest.mark.parametrize("key", KEYS)
def test_key_resolves_to_static_show_parser(key):
    parser = get_parser(key)
    assert isinstance(parser, StaticShowParser)
    assert parser.EVENT_KEY == key


@pytest.mark.parametrize("key", KEYS)
def test_every_source_has_at_least_one_event(key):
    assert SHOWS[key]["events"], f"{key} has no events"


@pytest.mark.parametrize(
    "key,idx,event",
    EVENTS,
    ids=[f"{k}[{i}]" for k, i, _ in EVENTS],
)
def test_event_is_well_formed(key, idx, event):
    assert event["name"] and isinstance(event["name"], str)

    start = event["date_start"]
    assert isinstance(start, str) and _ISO.match(start), f"bad date_start: {start!r}"

    end = event.get("date_end")
    if end is not None:
        assert _ISO.match(end), f"bad date_end: {end!r}"
        assert end >= start, f"date_end {end} before date_start {start}"

    assert event["venue_name"] and isinstance(event["venue_name"], str)

    pc = event.get("venue_postcode")
    assert pc is None or isinstance(pc, str)

    lat, lng = event.get("latitude"), event.get("longitude")
    if lat is not None:
        assert -90 <= lat <= 90, f"latitude out of range: {lat}"
    if lng is not None:
        assert -180 <= lng <= 180, f"longitude out of range: {lng}"

    assert event.get("event_type") in _ALLOWED_EVENT_TYPES


@pytest.mark.parametrize("key", KEYS)
def test_valid_until_is_latest_event_date(key):
    events = SHOWS[key]["events"]
    expected = max((e["date_end"] or e["date_start"]) for e in events)
    assert SHOWS[key]["valid_until"] == expected


@pytest.mark.asyncio
async def test_fetch_and_parse_makes_no_network_call(monkeypatch):
    """StaticShowParser serves local data — it must not open an HTTP client."""

    def _boom(*args, **kwargs):
        raise AssertionError("StaticShowParser must not perform network I/O")

    monkeypatch.setattr(httpx, "AsyncClient", _boom)

    key = KEYS[0]
    events = await get_parser(key).fetch_and_parse("https://source.example/x")
    assert len(events) == len(SHOWS[key]["events"])
    # the source URL is injected onto every event
    assert all(e.url == "https://source.example/x" for e in events)


@pytest.mark.asyncio
async def test_fetch_and_parse_round_trips_seed_data():
    """Events emitted match the seed exactly (count + key fields)."""
    for key in KEYS:
        events = await get_parser(key).fetch_and_parse("u")
        seed = SHOWS[key]["events"]
        assert len(events) == len(seed)
        for emitted, src in zip(events, seed):
            assert emitted.name == src["name"]
            assert emitted.date_start == src["date_start"]
            assert emitted.venue_name == src["venue_name"]


def test_unknown_key_yields_no_events():
    """A StaticShowParser for a key absent from the seed returns []."""
    import asyncio

    class _Missing(StaticShowParser):
        EVENT_KEY = "definitely-not-a-real-key"

    assert asyncio.run(_Missing().fetch_and_parse("u")) == []


@pytest.mark.parametrize("key", KEYS)
def test_dates_are_iso(key):
    starts = [e["date_start"] for e in SHOWS[key]["events"]]
    assert all(isinstance(s, str) and _ISO.match(s) for s in starts)


def test_staleness_is_reportable():
    """Sanity: we can compute which sources need an annual refresh.

    This does NOT fail on stale data (past fixtures are valid history); it
    asserts the staleness signal is computable, which the future staleness
    alert will consume. See parser audit recommendation S2/S3.
    """
    today = date.today().isoformat()
    stale = [k for k in KEYS if SHOWS[k]["valid_until"] < today]
    assert all(isinstance(SHOWS[k]["valid_until"], str) for k in KEYS)
    assert set(stale) <= set(KEYS)  # informational subset
