# Best Practices Audit

> Common pitfalls for scraping aggregators and how EquiCalendar avoids (or should avoid) them.

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

## 2. Data Quality

### Pitfall: Venue name proliferation

The same physical venue can appear under 20+ spellings across different sources.
"Eland Lodge", "Eland Lodge Equestrian Centre", "Eland Lodge EC", "ELAND LODGE
EQUESTRIAN" all refer to one place.

**Current mitigations**:
- `normalise_venue_name()` strips suffixes, title-cases, applies aliases
- Venues table provides a single source of truth for coordinates

**Recommended additions**:
- **Fuzzy matching on insert**: Before creating a new venue record, check if
  any existing venue has a Levenshtein distance < 3. Flag for manual review.
- **Periodic venue audit**: Query distinct `venue_name` values and cluster by
  similarity. Surface groups with 2+ names to a maintenance dashboard.

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

`POST /api/scans`, `POST /api/sources`, `DELETE /api/sources` are open to anyone
who can reach the app.

**Current mitigations**:
- Docker binds to `127.0.0.1:8001` only — not exposed to the internet

**Recommendations for production exposure**:
- Add API key authentication for write endpoints
- Consider basic auth or OAuth2 for the sources management UI
- Rate-limit the scan trigger endpoint to prevent abuse

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

**Recommendations**:
- Document the backup procedure (`docker cp` the .db file)
- Add a periodic backup script (cron job that copies to host or S3)
- For production: migrate to PostgreSQL with managed backups

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
