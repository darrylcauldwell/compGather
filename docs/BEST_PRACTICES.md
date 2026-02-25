# Engineering Practices & Best Practices

> Architecture patterns, design principles, and common pitfalls for scraping aggregators.

---

## Design Principles

### Pure Extraction Pattern

**Core Rule**: Parsers extract only; they do not filter or classify.

All parsers should:
- ✅ Extract **all** events from a source (past, present, future)
- ✅ Return raw data as found, including hints (discipline, description, classes)
- ❌ NOT filter by date (e.g., `if not is_future_event(date): continue`)
- ❌ NOT classify events (e.g., `discipline, is_comp = classify_event(name)`)
- ❌ NOT perform business logic (determining is_competition, type, etc.)

**Why**: Separation of concerns. Parser responsibility is extraction; classification
happens in `EventClassifier` during scanning. This makes parsers simpler, testable,
and resilient to classification rule changes.

**Example (Wrong)**:
```python
# BAD: Parser is doing classification
def fetch_and_parse(self, url):
    for item in items:
        if not is_future_event(item.date):  # ❌ Filtering
            continue
        discipline, is_comp = classify_event(item.name)  # ❌ Classification
        if is_comp:
            results.append(item)  # ❌ Only keeping competitions
```

**Example (Right)**:
```python
# GOOD: Parser extracts everything; classification happens in scanner
def fetch_and_parse(self, url):
    for item in items:
        result = ExtractedEvent(
            name=item.name,
            date_start=item.date,  # Extract all dates, no filtering
            discipline=infer_discipline(item.name),  # Raw hint only
            description=item.description,
            # ... other fields
        )
        results.append(result)  # All events extracted
```

### Service-Oriented Architecture

The application follows a layered service architecture:

```
Routers (HTTP endpoints)
    ↓
Services (business logic)
    ├── Scanner (orchestrates extraction pipeline)
    ├── EventClassifier (determines event type)
    ├── VenueMatcher (resolves venue identity)
    ├── Geocoder (resolves coordinates)
    └── Scheduler (triggers scans)
    ↓
Parsers (extract from sources)
    ├── Specific parsers (per-source)
    └── Generic parser (LLM fallback)
    ↓
Database Layer (SQLAlchemy ORM)
```

**Benefits**:
- Clear responsibility boundaries
- Easy to test services in isolation
- Changes to one service don't cascade
- Dependency injection makes testing straightforward

### Registry Pattern for Parsers

Parsers self-register via decorator:

```python
@register_parser("british_showjumping")
class BritishShowjumpingParser(BaseParser):
    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        ...
```

**Mechanism**:
1. `@register_parser` decorator stores class in a module-level registry dict
2. `app/parsers/__init__.py` imports all parser modules (triggers registration)
3. `get_parser(key)` looks up by key; returns instance or falls back to GenericParser
4. Adding a new parser requires only: 1) implement class, 2) import in `__init__.py`

**Advantages**:
- No central file to update (no `if key == "x": return XParser()`)
- Extensible: new parsers auto-register on import
- Testable: tests can mock parser registry

---

## 1. Scraping Reliability

### Pitfall: Source websites change without warning

Parsers break silently when a source site redesigns, changes CSS selectors, or
restructures their API. You discover weeks later that a source has zero results.

**Current mitigations**:
- `audit_disciplines()` logs unmapped values (symptom of parser changes)
- Scan records track `competitions_found` count and `error` messages
- Sources page shows last scan status with visual badges

**Recommended additions**:
- **Threshold alerting**: If a scan returns <50% of the previous count, log a
  warning and (eventually) send a notification. A parser returning 0 events
  should be treated as an error, not a success.
- **Parser smoke tests**: Each parser should have a minimal test with a fixture
  HTML file. Run in CI to catch regressions before deploy.
- **Source-level `expected_min_count`**: Store the typical event count per source
  and alert when actual is far below expected.

### Pitfall: Rate limiting and IP blocks

Aggressive scraping can trigger rate limits or IP bans, especially on
smaller sites (Epworth, Kelsall Hill) or APIs with undocumented limits (BS).

**Current mitigations**:
- Single daily scan (06:00) keeps frequency low
- Sequential scanning (one source at a time) avoids burst traffic

**Recommended additions**:
- **Per-source delays**: Add a configurable `min_delay_seconds` per source.
  Start with 1-2 seconds between requests to the same domain.
- **Exponential backoff on HTTP 429/503**: Retry with increasing delays.
- **User-Agent header**: All parsers should send a consistent, identifiable
  `User-Agent: EquiCalendar/1.0 (+https://github.com/darrylcauldwell/compGather)`.

### Pitfall: Playwright resource leaks

Playwright browsers consume significant memory. If a browser instance isn't
properly closed after an error, it accumulates and eventually crashes the container.

**Recommendations**:
- Always use `async with` context managers for browser and page objects
- Set a hard timeout per parser (e.g. 60 seconds)
- Monitor container memory usage; the Docker healthcheck catches OOM indirectly

---

## EventClassifier: Single Source of Truth

The `EventClassifier` service is responsible for determining event type across the
entire application. No other code should duplicate this logic.

### How It Works

```python
# In scanner.py during event processing:
discipline, is_competition = EventClassifier.classify(
    name=extracted_event.name,
    discipline_hint=extracted_event.discipline,
    description=extracted_event.description or ""
)

# Returns:
# - discipline: Normalized canonical value (e.g., "Show Jumping", "Training", None)
# - is_competition: Boolean indicating if event is a competition
```

### Classification Strategy

1. **Non-competition keywords**: Check name/description for "Training", "Clinic", "Venue Hire"
2. **Normalize discipline hint**: If parser provided a discipline, normalize it
3. **Competition keywords**: Check name/description for "Show", "Competition", "XC", etc.
4. **Default**: If no match, return `(None, True)` — assume competition unless proven otherwise

### Why This Pattern

- **Single Responsibility**: EventClassifier owns all classification logic
- **Testable**: Unit test classification rules with parametrized test cases
- **Maintainable**: Change rules in one place; affects entire app
- **Replaceable**: Can swap strategy (e.g., ML classifier) without touching parsers/scanner
- **Prevents Drift**: No scattered `classify_event()` calls in 16 different parsers

### Adding New Classification Rules

To handle a new event type:

1. Add keyword check to `EventClassifier.classify()`:
```python
if "masterclass" in name.lower() or "masterclass" in description.lower():
    return ("Training", False)
```

2. Add test case:
```python
def test_masterclass_is_training():
    disc, is_comp = EventClassifier.classify("Mary's Masterclass")
    assert is_comp is False
    assert disc == "Training"
```

3. No parser changes needed. All parsers automatically use the new rule.

---

## 2. Data Quality

### Pitfall: Venue name proliferation

The same physical venue can appear under 20+ spellings across different sources.
"Eland Lodge", "Eland Lodge Equestrian Centre", "Eland Lodge EC", "ELAND LODGE
EQUESTRIAN" all refer to one place.

**Current mitigations (three layers of defence)**:
1. **`normalise_venue_name()`** — catches most variants at ingest time:
   - Iterative suffix stripping (handles "X Equestrian Centre Ltd" across passes)
   - 30+ common suffixes (equestrian, equine, riding, etc.)
   - Address truncation: strips trailing address parts after commas
   - Junk guards: rejects URLs, postcodes, plus codes, very long strings (>100 chars)
2. **`venue_seeds.json` aliases** (230+ entries) — known spelling corrections and
   event-name-to-venue mappings (e.g. "Royal Bath & West Show" → "Royal Bath & West Showground")
3. **`VenueIndex.prefix_match()`** — safety net catches incomplete suffix stripping.
   If "Allens Hill" (known) is a prefix of "Allens Hill Competition & Livery Centre"
   (incoming), auto-matches. Only fires when unambiguous (one unique venue_id).

**Results**: 661 unique venues from 6,295 competitions across 26 sources.
Zero exact duplicates. One legitimate multi-venue postcode (two showgrounds
in rural Cornwall sharing TR3 7DP).

**Ongoing maintenance**:
- When a new venue variant appears: add to the venue's `"aliases"` array in
  `app/venue_seeds.json`, rebuild, then run `scripts/renormalise_venues.py`
  to fix existing DB records
- British Showjumping county shows use event names as venue names — these need
  manual alias mapping when new shows appear

### Pitfall: Discipline category drift

New parsers or source changes introduce raw discipline values that bypass
the canonical mapping. Over time, the filter dropdown accumulates garbage.

**Current mitigations**:
- `normalise_discipline()` maps 70+ raw values to 15 canonical categories
- `audit_disciplines()` runs after scheduled scans, logs and auto-fixes drift

**This is well-handled.** The two-layer approach (at-scrape normalisation +
periodic audit) is robust. Keep the canonical list in sync when adding new
parsers.

### Pitfall: Duplicate events across sources

The same competition can be listed on multiple sites (e.g. a BS event appears
on britishshowjumping.co.uk AND horse-events.co.uk AND horsemonkey.com). The
current dedup key `(source_id, name, date_start, venue_name)` prevents
duplicates within a source but not across sources.

**Recommendations**:
- **Cross-source dedup**: After upserting, check for records with the same
  `(name, date_start, venue_name)` but different `source_id`. Mark the
  secondary as a duplicate and link to the primary. Show only primary in the
  default view.
- **Merge strategy**: Keep the record from the most authoritative source
  (BS > Horse Events > HorseMonkey). Accumulate supplementary data (URL,
  classes, postcode) from secondaries.

---

## 3. Performance

### Pitfall: N+1 queries on the main page

Loading competitions with their source relationship can generate N+1 queries
if eager loading is misconfigured.

**Current mitigations**:
- `selectinload(Competition.source)` in the main query — correct approach

**This is well-handled.**

### Pitfall: Full table scan on every page load

The main page query touches every future competition row to count, then
fetches 50 with OFFSET.

**Current mitigations**:
- Pagination limits data transfer to 50 rows per page

**Recommended additions**:
- **Database indexes**: Add indexes on `(date_start, is_competition)` and
  `(discipline)` and `(venue_name)`. SQLite will benefit significantly from
  these for the WHERE + ORDER BY clauses.
- **COUNT caching**: Cache the total count for 5 minutes; avoid running
  `SELECT COUNT(*)` on every page load. The count changes only after scans.

```sql
CREATE INDEX IF NOT EXISTS idx_comp_date_active
ON competitions (date_start, is_competition)
WHERE is_competition = 1;

CREATE INDEX IF NOT EXISTS idx_comp_discipline
ON competitions (discipline);

CREATE INDEX IF NOT EXISTS idx_comp_venue
ON competitions (venue_name);
```

### Pitfall: Unbounded API responses

`GET /api/competitions` returns all matching records with no pagination.
A request without filters returns 7,000+ records as JSON.

**Recommendations**:
- Add `limit` and `offset` parameters to the API endpoint (default limit: 100)
- Return total count in response headers or a wrapper object
- Consider cursor-based pagination for the API (more stable under concurrent writes)

---

## 4. Security

### Pitfall: SQL injection via filter parameters

Inline string interpolation in SQL queries is a classic vulnerability.

**Current mitigations**:
- SQLAlchemy parameterised queries throughout — no raw SQL with string formatting
- The venue search uses `ilike(f"%{venue.strip()}%")` which SQLAlchemy
  parameterises correctly

**This is well-handled.** SQLAlchemy's expression language prevents injection
by design.

### Pitfall: Stored XSS from scraped data

Competition names, venue names, and URLs come from untrusted external sources.
If rendered unescaped in HTML, malicious content could execute scripts.

**Current mitigations**:
- Jinja2 auto-escapes all `{{ variable }}` output by default

**This is well-handled.** Jinja2's auto-escaping is the correct defence.
The `| safe` filter is not used on user-controlled data.

### Pitfall: Open redirect via URL field

Competition URLs come from scrapers and are rendered as `<a href="{{ link }}">`.
A malicious source could inject `javascript:` URLs.

**Recommendations**:
- Validate that all stored URLs start with `http://` or `https://`
- Strip or reject URLs with other schemes during the scrape phase

### Pitfall: No authentication on admin endpoints

**Current mitigations**:
- Write API endpoints (`POST /api/scans`, source CRUD) require `X-API-Key` header
- Sources are auto-seeded from code (`_SOURCE_DEFS` in scanner.py) — no runtime
  creation needed
- Admin UI (`GET /admin`) is a hidden page with no navigation link; provides
  scan triggers only (no disable/delete controls)
- Docker binds to `127.0.0.1:8001` only in dev

---

## 5. Operational Reliability

### Pitfall: No migration framework

Schema changes are handled by `ALTER TABLE` in `init_db()` with a try/except
to skip if the column exists. This works but doesn't track migration history
or support rollbacks.

**Recommendations**:
- Adopt Alembic with `--autogenerate` support
- Store migration files in `alembic/versions/`
- Run migrations in the Docker entrypoint before starting uvicorn

### Pitfall: Data loss on container recreation

SQLite file is stored in a Docker named volume (`compgather_data`). This
survives container recreates but NOT `docker compose down -v`.

**Current mitigations (data resilience)**:
- **Source auto-seeding**: All 26 sources defined in `_SOURCE_DEFS` in scanner.py.
  `seed_sources()` runs on startup — a fresh DB auto-creates all sources.
- **Venue seed data**: `app/venue_seeds.json` provides known postcodes, coordinates,
  and aliases for ~570 venues. `seed_venue_postcodes()` runs on startup.
- **Venue aliases**: 230+ aliases from `venue_seeds.json` migrated to DB on startup.
- **British Dressage seed**: Temporary JSON fallback (`british_dressage_seed.json`)
  ships in the Docker image for when the BD API is down.
- **Full rebuild tested**: `docker compose down -v && docker compose up -d --build`
  + full rescan recovers all data from source websites.
- Backup script: `scripts/backup.sh` (7-day rotation)

**For production**: migrate to PostgreSQL with managed backups.

### Pitfall: No structured logging

Current logging uses Python's `logging` with `%(message)s` format. Log output
is human-readable but not machine-parseable.

**Recommendations**:
- Add `structlog` or JSON logging format for production
- Include: timestamp, level, source_id, parser_key, competitions_found, duration
- Makes log aggregation (ELK, Loki) feasible

---

## 6. Testing

### Current state: Minimal

3 test files covering: scanner pipeline (mocked), LLM extractor parsing,
and haversine calculation. No parser-level tests, no API endpoint tests,
no frontend tests.

**Recommendations**:

| Layer | What to test | Approach |
|-------|-------------|----------|
| **Parsers** | Each parser against a fixture HTML file | Save a sample page, assert correct `ExtractedCompetition` output |
| **Normalisation** | Venue and discipline edge cases | Unit tests with parametrize |
| **API endpoints** | CRUD operations, pagination, filters | `httpx.AsyncClient` with `TestClient` |
| **iCal export** | Valid RFC 5545 output | Parse generated .ics and assert VEVENT properties |
| **Geocoding** | Cache behaviour, fallback chain | Mock HTTP responses |
| **Integration** | Full scan pipeline | In-memory DB + mocked HTTP (existing approach is good) |

**Target**: >80% coverage on `app/parsers/utils.py`, `app/services/scanner.py`,
and `app/routers/`. Parsers are harder to test (fragile fixtures) but each
should have at least one happy-path test.

---

## 7. Error Handling & Resilience

### Parser Failure Modes

Parsers can fail in several ways:

| Failure | Symptom | Recovery |
|---------|---------|----------|
| **Source offline** | HTTP 500, connection timeout | Scan retries; old data kept; marked as stale |
| **Source changed structure** | 0 competitions returned | Threshold alert; manual parser fix required |
| **Invalid event data** | Missing required fields | Skip event, log warning, continue scanning |
| **Rate limiting** | HTTP 429 | Backoff + retry in future scan |
| **Playwright crash** | Browser OOM | Container restart; APScheduler reschedules |

### Mitigation Strategies

**1. Graceful Degradation**
- If a parser fails, scanning continues with other sources
- Old data is retained (competitions aren't deleted if a source fails)
- Events marked with `last_seen_at` track freshness

**2. Threshold Alerting**
Monitor `competitions_found` count per source:
- If count drops >50% vs. previous scan → log warning
- If count is 0 → treat as error (possible parser breakage)
- Alerts integrate with monitoring stack (Grafana)

**3. Timeout & Resource Limits**
- Parser timeout: 60 seconds hard limit
- Playwright memory limit: container memory constraint
- HTTP timeout: 30 seconds with connect timeout

**4. Validation at Ingest**
```python
# In scanner.py: validate extracted event
try:
    parsed_date = datetime.fromisoformat(comp_data.date_start)
except ValueError:
    logger.warning(f"Invalid date for {comp_data.name}: {comp_data.date_start}")
    continue  # Skip this event, don't crash
```

**5. Database Transactions**
- Scanner wraps all upserts in transactions
- Partial failures don't leave DB in inconsistent state
- Scan record tracks `status` (pending, running, completed, failed)

---

## 8. Code Organization Principles

### File Structure by Responsibility

- **`app/models.py`**: SQLAlchemy ORM models (no business logic)
- **`app/schemas.py`**: Pydantic request/response + ExtractedEvent (data contracts)
- **`app/services/`**: Business logic (Scanner, EventClassifier, VenueMatcher, Geocoder)
- **`app/parsers/`**: Data extraction (all parsers extend BaseParser)
- **`app/routers/`**: HTTP endpoints (thin wrappers around services)
- **`app/parsers/utils.py`**: Shared utilities (normalisation, regex, inference)

**Why**: Clear separation of concerns. Models don't contain logic. Services don't
know about HTTP. Routers don't contain business logic. Easy to test, refactor, extend.

### Async/Await Principles

The entire stack is async:

```python
# ✅ Good: All async, proper awaits
async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
    return results

# ✅ Good: Gather multiple async operations
tasks = [parser.fetch_and_parse(url) for parser in parsers]
results = await asyncio.gather(*tasks)

# ❌ Bad: Blocking call in async context
import requests  # ← blocking HTTP
resp = requests.get(url)  # ← blocks entire event loop

# ❌ Bad: No await on async function
task = fetch_data()  # ← Task object, never executed
```

**Rationale**: Equestrian sources are slow (1-5s per source). Concurrent fetching
reduces total scan time from ~2 minutes (sequential) to ~20 seconds (parallel).

### Type Hints & Validation

**Use Pydantic for all external data**:
```python
# Schema for parser output (validated at extraction time)
class ExtractedEvent(BaseModel):
    name: str  # Required
    date_start: str  # ISO format
    discipline: str | None = None  # Optional
    has_pony_classes: bool = False  # Default

# Usage: Parser returns ExtractedEvent instances
# Pydantic validates on construction; invalid data raises ValidationError
```

**Use type hints for function signatures**:
```python
async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
    ...

def normalise_venue_name(raw: str) -> str:
    ...
```

**Benefits**: IDE autocomplete, type checking with `mypy`, self-documenting code.

---

## 9. Recent Lessons: Abbey Farm Training Clinics Issue

### The Problem

Training clinic events detected by Abbey Farm parser but missing from the UI. Investigation revealed a **logic bug caused by scattered classification responsibilities**.

### Root Cause

Multiple systems were trying to classify events:

1. Parser called `classify_event("Maddy Moffet Training Clinic")` → `("Training", False)`
2. Parser ignored the `is_competition=False` return value (logic was lost)
3. Scanner called `normalise_discipline()` on the parser's discipline hint → `(None, True)`
4. Scanner checked parser result and tried to override → complex 13-line override logic
5. Result: `is_competition=True` was stored, but event was actually training → hidden from default view

### The Solution

**Centralize all classification in EventClassifier; parser is purely extractive.**

**Before** (scattered logic):
```python
# In parser:
disc, is_comp = classify_event(name)  # ← Parser classifies
parsed_event = ExtractedCompetition(
    name=name,
    discipline=disc,
    # ← is_competition NOT in schema
)

# In scanner:
disc, is_comp = normalise_discipline(comp.discipline)
name_disc, name_is_comp = classify_event(comp.name)  # ← Re-classifying!
if not name_is_comp:
    is_competition = False
    if not disc or disc == comp.discipline:  # ← Complex override logic
        disc = name_disc
```

**After** (single source of truth):
```python
# In parser:
parsed_event = ExtractedEvent(
    name=name,
    discipline=infer_discipline(name),  # ← Just a hint, no classification
    description=description,
    # ← No is_competition; not parser's job
)

# In scanner:
disc, is_comp = EventClassifier.classify(
    name=comp.name,
    discipline_hint=comp.discipline,
    description=comp.description
)
# ← All classification logic in one place, tested independently
```

### Lessons Learned

1. **Single Responsibility**: Each component should have one reason to change.
   - Parser: changes when source structure changes
   - EventClassifier: changes when classification rules change
   - Scanner: changes when pipeline logic changes

2. **Don't Scatter Logic**: When classification logic lives in 16 different parsers
   AND in the scanner, bugs are inevitable. Bugs become architectural.

3. **Pure Functions Are Easier to Test**: `EventClassifier.classify()` can be unit
   tested with 20 parametrized cases. No HTTP mocking, no DB needed.

4. **Composition Over Inheritance**: Use services that call other services, not
   base classes with overrideable methods.

---

## 10. Checklist: Adding a New Parser

When adding a new equestrian event source:

- [ ] **Create** `app/parsers/source_name.py`
- [ ] **Extend** `BaseParser` abstract class
- [ ] **Implement** `fetch_and_parse()` → `list[ExtractedEvent]`
- [ ] **Extract** all events (no filtering by date or type)
- [ ] **Populate** all ExtractedEvent fields available from source
  - `name`, `date_start`, `venue_name` required
  - `discipline` optional (use `infer_discipline()` if available)
  - `description` optional but helps EventClassifier
- [ ] **Register** with `@register_parser("key")`
- [ ] **Import** in `app/parsers/__init__.py` (triggers registration)
- [ ] **Add source** to `_SOURCE_DEFS` in `app/services/scanner.py`
- [ ] **Test** with fixture HTML; verify ExtractedEvent output
- [ ] **Document** in `CONTRIBUTING.md` if source has quirks

**Remember**: Your parser is purely extractive. Classification rules, filtering,
and business logic belong in services, not in the parser.
