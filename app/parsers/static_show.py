"""Data-driven parser for static (hard-coded) show fixtures.

Many high-profile shows publish their calendar in formats that don't repay a
bespoke scraper (annual, JS-heavy, or no machine-readable listing). For these
the fixtures are curated by hand and updated annually. Rather than ~80
near-identical one-off parser files that fetched a URL and discarded the
response, all such fixtures live in ``static_shows.json`` and are served by a
single :class:`StaticShowParser`.

Each JSON key is a ``parser_key`` registered in the scanner's ``_SOURCE_DEFS``.
A dynamic subclass is registered per key at import time, so ``get_parser(key)``
resolves exactly as it did for the old per-show classes.

Unlike the old stubs, this parser performs **no HTTP request** — the data is
local, so there is nothing to fetch. The ``url`` passed to
:meth:`fetch_and_parse` (the source URL) is attached to every event, preserving
the previous behaviour.

``valid_until`` (the latest event date per key) is stored for the staleness
check: a source whose fixtures are all in the past needs an annual refresh.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

_DATA: dict[str, dict[str, Any]] | None = None

# Fields carried verbatim from the JSON seed into each ExtractedEvent.
_EVENT_FIELDS = (
    "name",
    "date_start",
    "date_end",
    "venue_name",
    "venue_postcode",
    "latitude",
    "longitude",
    "discipline",
    "event_type",
)


def get_static_shows() -> dict[str, dict[str, Any]]:
    """Return {parser_key: {"valid_until": str, "events": [...]}}. Cached."""
    global _DATA
    if _DATA is None:
        path = Path(__file__).with_name("static_shows.json")
        with open(path, encoding="utf-8") as f:
            _DATA = json.load(f)
    return _DATA


class StaticShowParser(BaseParser):
    """Serve hard-coded show fixtures for one ``EVENT_KEY`` from the JSON seed.

    Subclasses set ``EVENT_KEY``; instances are created by the registry. No
    network request is made — fixtures are local data.
    """

    EVENT_KEY: str = ""

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        record = get_static_shows().get(self.EVENT_KEY)
        if not record:
            logger.warning("StaticShowParser: no fixtures for key %r", self.EVENT_KEY)
            return []

        # Curated shows are all spectator-worthy (Watch tab); event_type decides
        # whether they're also enterable (competition → Compete tab).
        events = [
            ExtractedEvent(**{f: ev.get(f) for f in _EVENT_FIELDS}, url=url, spectator=True)
            for ev in record.get("events", [])
        ]
        logger.info("%s: %d static fixture(s)", self.EVENT_KEY, len(events))
        return events


def _register_static_shows() -> None:
    """Register one StaticShowParser subclass per key in the JSON seed."""
    for key in get_static_shows():
        cls = type(
            f"StaticShow_{key}",
            (StaticShowParser,),
            {"EVENT_KEY": key, "__doc__": f"Static fixtures for {key!r}."},
        )
        register_parser(key)(cls)


_register_static_shows()
