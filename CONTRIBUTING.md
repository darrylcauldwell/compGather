# Contributing to EquiCalendar

## Adding a New Parser

Each competition source has its own parser module in `app/parsers/`. To add a new one:

### 1. Create the parser module

Create `app/parsers/my_source.py`:

```python
from __future__ import annotations

import logging

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, extract_postcode, infer_discipline, is_future_event
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)


@register_parser("my_source")
class MySourceParser(BaseParser):
    """Parser for example.com — brief description of site structure."""

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        competitions: list[ExtractedCompetition] = []

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        for item in soup.select(".event-card"):
            name = item.select_one(".title").get_text(strip=True)
            date_str = item.select_one(".date").get_text(strip=True)
            # Parse date_str into YYYY-MM-DD format
            date_start = ...

            if not is_future_event(date_start):
                continue

            venue = item.select_one(".venue").get_text(strip=True)
            postcode = extract_postcode(venue)

            competitions.append(ExtractedCompetition(
                name=name,
                date_start=date_start,
                venue_name=venue,
                venue_postcode=postcode,
                discipline=infer_discipline(name),
                has_pony_classes=detect_pony_classes(name),
                url=url,
            ))

        logger.info("MySource: extracted %d competitions", len(competitions))
        return competitions
```

### 2. Register the parser

Add an import to `app/parsers/__init__.py` (alphabetical order):

```python
from app.parsers import my_source  # noqa: F401
```

The import triggers `@register_parser("my_source")`, adding it to the registry.

### 3. Add a source record

Via the API:

```bash
curl -X POST http://localhost:8001/api/sources \
  -H "Content-Type: application/json" \
  -d '{"name": "My Source", "url": "https://example.com/events", "parser_key": "my_source"}'
```

Then trigger a scan:

```bash
curl -X POST http://localhost:8001/api/scans \
  -H "Content-Type: application/json" \
  -d '{"source_id": <id>}'
```

### 4. Write a test

Create a fixture file in `tests/fixtures/` with sample HTML/JSON from the source, then add a test in `tests/test_parsers.py` following the existing pattern:

```python
@pytest.mark.asyncio
async def test_my_source_parser():
    fixture = FIXTURES / "my_source_events.html"
    parser = MySourceParser()
    with patch.object(httpx.AsyncClient, "get", return_value=_mock_response(fixture)):
        results = await parser.fetch_and_parse("https://example.com/events")
    assert len(results) >= 1
    assert results[0].venue_name == "Expected Venue"
```

## Key Patterns

### ExtractedCompetition fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | `str` | Yes | Event name |
| `date_start` | `str` | Yes | `YYYY-MM-DD` format |
| `date_end` | `str` | No | For multi-day events |
| `venue_name` | `str` | Yes | Normalised by scanner before storage |
| `venue_postcode` | `str` | No | UK postcode for geocoding |
| `latitude` | `float` | No | If source provides coordinates directly |
| `longitude` | `float` | No | If source provides coordinates directly |
| `discipline` | `str` | No | e.g. Show Jumping, Dressage, Eventing |
| `has_pony_classes` | `bool` | No | Defaults to `False` |
| `classes` | `list[str]` | No | Individual class descriptions |
| `url` | `str` | No | Direct link to event page |

### Shared utilities (`app/parsers/utils.py`)

- `extract_postcode(text)` — finds first UK postcode in text
- `detect_pony_classes(text)` — checks for pony/junior keywords
- `infer_discipline(name)` — guesses discipline from event name
- `is_future_event(date_start, date_end)` — filters past events
- `normalise_venue_name(name)` — strips suffixes, applies aliases

### Deduplication

The scanner upserts on `(source_id, name, date_start, venue_name)`. The `name` must match exactly for dedup to work, so avoid adding extra whitespace or changing capitalisation between scans.

### Venue coordinates

If the source provides lat/lng directly (e.g. Horse Monkey), set them on `ExtractedCompetition`. Otherwise, provide `venue_postcode` and the scanner's `_backfill_venue_data()` will geocode it.

For single-venue sources (e.g. Epworth), hardcode the venue name and postcode as constants.

## Running Tests

Tests run inside the Docker container:

```bash
# Copy tests into container and run
docker compose cp tests/ compgather:/app/tests/
docker compose exec compgather pytest tests/ -v

# Run a single test file
docker compose exec compgather pytest tests/test_parsers.py -v
```

## Code Style

- Linter: `ruff check app/`
- All code uses `from __future__ import annotations`
- Async throughout — use `httpx.AsyncClient` (not `requests`)
- Log at `INFO` level for summary counts, `DEBUG` for per-page details
