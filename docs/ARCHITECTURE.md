# EquiCalendar Architecture

> Covers the current system design, data flow, and recommended evolution path.

---

## 1. System Overview

EquiCalendar is a **scrape-normalise-store-serve** pipeline that aggregates UK equestrian competition data from 26 heterogeneous sources into a single searchable interface.

```
                       +-------------------+
                       |   26 Source Sites  |
                       | (BS, BE, BD, PC,  |
                       |  HorseMonkey ...) |
                       +---------+---------+
                                 |
                        HTTP / Playwright
                                 |
                       +---------v---------+
                       |     Parsers       |
                       |  (per-source or   |
                       |   LLM generic)    |
                       +---------+---------+
                                 |
                      ExtractedCompetition[]
                                 |
                       +---------v---------+
                       |     Scanner       |
                       | - normalise venue |
                       | - normalise disc. |
                       | - geocode         |
                       | - dedup & upsert  |
                       +---------+---------+
                                 |
                       +---------v---------+
                       |     SQLite DB     |
                       | competitions      |
                       | venues / sources  |
                       +---------+---------+
                                 |
                    +------------+------------+
                    |                         |
           +--------v--------+     +---------v--------+
           |   HTML pages    |     |    REST API      |
           | (Jinja2 + HTMX) |     | /api/competitions|
           +-----------------+     | /api/sources     |
                                   | /api/scans       |
                                   +------------------+
```

---

## 2. Directory Structure

```
compGather/
├── app/
│   ├── config.py              # pydantic-settings: env vars
│   ├── database.py            # async SQLAlchemy engine + migrations
│   ├── main.py                # FastAPI lifespan, router wiring
│   ├── models.py              # SQLAlchemy ORM models
│   ├── schemas.py             # Pydantic request/response + ExtractedCompetition
│   ├── parsers/
│   │   ├── __init__.py        # auto-imports all parsers (triggers registration)
│   │   ├── base.py            # BaseParser ABC
│   │   ├── registry.py        # @register_parser decorator + get_parser()
│   │   ├── utils.py           # shared: postcode regex, discipline normalisation,
│   │   │                      #   venue normalisation, pony detection, JSON-LD
│   │   ├── generic.py         # LLM fallback via Ollama
│   │   ├── british_showjumping.py
│   │   ├── british_dressage.py
│   │   ├── british_eventing.py
│   │   └── ... (26 parsers total)
│   ├── routers/
│   │   ├── health.py          # GET /health
│   │   ├── pages.py           # GET / (competitions table), GET /sources
│   │   ├── competitions.py    # REST API + iCal export
│   │   ├── sources.py         # CRUD for sources
│   │   └── scanner.py         # POST /api/scans trigger
│   ├── services/
│   │   ├── scanner.py         # scan orchestration, upsert, venue backfill,
│   │   │                      #   discipline audit
│   │   ├── scheduler.py       # APScheduler daily cron
│   │   ├── geocoder.py        # postcodes.io + Nominatim + haversine
│   │   ├── fetcher.py         # HTTP helpers
│   │   └── extractor.py       # LLM extraction for generic parser
│   ├── static/css/
│   │   └── input.css          # Tailwind source with CSS custom properties
│   └── templates/
│       ├── base.html          # layout: header, nav, footer, theme toggle
│       ├── competitions.html  # table + filters + pagination + iCal icons
│       └── sources.html       # source management + scan status
├── scripts/
│   └── seed_new_sources.py    # one-off data seeding
├── tests/
│   ├── test_scanner.py        # scan pipeline integration tests (in-memory DB)
│   ├── test_extractor.py      # LLM response parsing
│   └── test_geocoder.py       # haversine calculations
├── Dockerfile                 # multi-stage: Node (CSS) + Python (app)
├── docker-compose.yml         # dev: ports, volumes, healthcheck
├── docker-compose.prod.yml    # production overrides
├── requirements.txt           # Python deps (pinned)
├── package.json               # Node deps for Tailwind build
├── tailwind.config.js
└── postcss.config.js
```

---

## 3. Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Runtime** | Python 3.13, async | Native async I/O for concurrent HTTP scraping |
| **Framework** | FastAPI | Async-native, auto-generated OpenAPI docs, Pydantic validation |
| **ORM** | SQLAlchemy 2.0 (async) | Mature, type-safe mapped columns, async session support |
| **Database** | SQLite via aiosqlite | Zero-ops, single-file, sufficient for read-heavy single-user workload |
| **Templating** | Jinja2 | Server-rendered HTML; avoids SPA complexity for a data table |
| **CSS** | Tailwind 4 + custom properties | Utility-first; CSS variables enable dark/light toggle without JS rebuild |
| **Browser automation** | Playwright (Chromium) | Required for JS-rendered sources (MyRidingLife, ASAO) |
| **Scheduling** | APScheduler | In-process cron; no external job queue needed |
| **Geocoding** | postcodes.io + Nominatim | Free, no API keys; Nominatim covers Crown Dependencies |
| **LLM fallback** | Ollama (qwen2.5:1.5b) | Local model for generic parser; no API costs |
| **Container** | Docker multi-stage | Node stage builds CSS, Python stage runs app; ~400MB image |

---

## 4. Data Models

### Competition (primary entity)

| Column | Type | Notes |
|--------|------|-------|
| `id` | int PK | Auto-increment |
| `source_id` | int FK | Links to `sources.id` |
| `name` | text | Event name as scraped |
| `date_start` | date | Start date (ISO) |
| `date_end` | date? | End date for multi-day events |
| `venue_name` | text | Normalised via `normalise_venue_name()` |
| `venue_postcode` | text? | UK postcode |
| `latitude` | float? | From venues table, parser, or geocoder |
| `longitude` | float? | As above |
| `distance_miles` | float? | Haversine from home postcode |
| `discipline` | text? | Normalised to ~15 canonical values |
| `has_pony_classes` | bool | Keyword detection on event name/classes |
| `is_competition` | bool | False for venue hire, training, clinics |
| `url` | text? | Direct link to source event page |
| `raw_extract` | text? | JSON dump of original parsed data |
| `first_seen_at` | datetime | When first scraped |
| `last_seen_at` | datetime | Most recent scan that found it |

**Dedup key**: `(source_id, name, date_start, venue_name)`

### Venue (lookup/cache)

| Column | Type | Notes |
|--------|------|-------|
| `name` | text UNIQUE | Normalised venue name |
| `postcode` | text? | Best-known postcode |
| `latitude` / `longitude` | float? | Cached geocode result |

### Source

Represents one scrape target (website URL + parser key).

### Scan

Audit log of each scan run (status, timing, error, competition count).

---

## 5. Data Flow: Scan Pipeline

```
1. Trigger
   ├── Scheduled: APScheduler cron (daily 06:00)
   ├── Manual: POST /api/scans {source_id}
   └── Manual: POST /api/scans {} (all enabled)

2. For each source:
   a. get_parser(source.parser_key) → parser instance
   b. parser.fetch_and_parse(url) → list[ExtractedCompetition]
   c. For each competition:
      i.   Parse dates → skip if invalid
      ii.  normalise_venue_name(raw_venue)
      iii. normalise_discipline(raw_discipline) → (canonical, is_competition)
      iv.  Resolve coordinates:
           venues table → parser coords → postcode geocode
      v.   Upsert on (source_id, name, date_start, venue_name)

3. Post-scan:
   a. _backfill_venue_data() — propagate coords across same-venue events
   b. audit_disciplines() — (scheduled scans only) fix any drift
```

---

## 6. Parser Architecture

All parsers extend `BaseParser` and are registered via decorator:

```python
@register_parser("british_showjumping")
class BritishShowjumpingParser(BaseParser):
    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        # site-specific scraping logic
        ...
```

**Registration**: Importing a parser module triggers `@register_parser`. All parsers
are imported in `app/parsers/__init__.py`.

**Lookup**: `get_parser(key)` returns the matching class instance, or falls back to
`GenericParser` (LLM-based) if the key is unknown or `None`.

### Parser strategies by source type

| Strategy | Parsers | Notes |
|----------|---------|-------|
| **HTML table scraping** | BS, BE, BSPS, BSHA, Horsevents, MyRidingLife | BeautifulSoup + httpx |
| **JSON API** | Equipe, BritishDressage, HorseMonkey, Addington | Direct API calls |
| **Sitemap crawling** | HorseEvents, OutdoorShows | Parse sitemap.xml, then individual pages |
| **WordPress plugin** | Ashwood (MEC), ASAO (Search Filter Pro) | Plugin-specific AJAX endpoints |
| **Fixed-venue** | Epworth, Hickstead, NVEC, Showground | Hardcoded venue name/postcode |
| **Document parsing** | DerbyCollege | .docx files via python-docx |
| **Playwright** | MyRidingLife | ASP.NET postback requires JS execution |
| **LLM fallback** | Generic | Ollama extracts structured data from HTML |

---

## 7. Normalisation Layers

### Venue normalisation (`normalise_venue_name`)
1. Strip BS show numbering: `"Arena (2) - SPONSORED BY..."` -> `"Arena"`
2. Strip trailing event descriptions: `"(Festival)"`, `"(Championship)"`
3. Title-case
4. Remove `"Limited"` suffix
5. Remove trailing abbreviation codes: `"- Chspc"`
6. Strip common suffixes: `"Equestrian Centre"`, `"Riding School"`, etc.
7. Apply known aliases: `"Southview"` -> `"South View"`

### Discipline normalisation (`normalise_discipline`)
- Maps ~70 raw values to 15 canonical categories
- 12 competition types: Show Jumping, Dressage, Eventing, Cross Country,
  Combined Training, Showing, Hunter Trial, Pony Club, NSEA,
  Agricultural Show, Endurance, Gymkhana
- 2 non-competition types: Venue Hire, Training
- 1 catch-all: Other
- Returns `(canonical_name, is_competition)` tuple

### Discipline inference (`infer_discipline`)
- Regex-based fallback when parser doesn't provide a discipline
- Matches keywords in event name: `"showjump"` -> Show Jumping, `"ODE"` -> Eventing

---

## 8. Geocoding Pipeline

```
                  +-----------+
                  |  Venue    |   1. Check venues table cache
                  |  Table    |      (fastest, no API call)
                  +-----+-----+
                        |
                  miss? |
                        v
                  +-----------+
                  |  Parser   |   2. Use coords from parser
                  |  Coords   |      (Horse Monkey provides lat/lng)
                  +-----+-----+
                        |
                  miss? |
                        v
               +--------+--------+
               | postcodes.io    |   3a. Active postcodes
               | (active)        |
               +--------+--------+
                        |
                  miss? |
                        v
               +--------+--------+
               | postcodes.io    |   3b. Terminated postcodes
               | (terminated)    |
               +--------+--------+
                        |
                  miss? |
                        v
               +--------+--------+
               |   Nominatim     |   4. Crown Dependencies (GY, JE, IM)
               | (OpenStreetMap) |      or any other fallback
               +--------+--------+
                        |
                        v
                  Store in venues table for future lookups
                  Calculate haversine distance from home
```

All coordinates are validated against a UK bounding box (49-61 lat, -11 to 2 lng)
to reject erroneous data.

---

## 9. Frontend Architecture

Server-rendered Jinja2 templates — no SPA, no client-side framework.

| Page | Route | Features |
|------|-------|----------|
| **Competitions** | `GET /` | Paginated table (50/page), column sorting, inline filter dropdowns (discipline, venue, pony), date range + distance filters, iCal download per row |
| **Sources** | `GET /sources` | Source CRUD, scan triggers, status badges, competition counts |

### Styling approach
- Tailwind 4 utility classes for layout
- CSS custom properties (`--cg-sky`, `--cg-bg`, etc.) for theming
- Dark theme default, light theme via `data-theme="light"` attribute
- Theme persisted in localStorage

### Client-side JavaScript (minimal)
- `sortBy(col)` — toggles sort direction, preserves filters via URL params
- `filterBy(param, value)` — sets URL param, resets to page 1
- `goToPage(n)` — pagination with filter preservation
- `updatePostcode()` — POST to API, reload on success
- `toggleDropdown(id)` — inline filter dropdowns

---

## 10. Recommended Architecture Evolution

### Short-term (current → 3 months)

**Migrate SQLite to PostgreSQL** when concurrent writes become a bottleneck.
SQLite's write lock means simultaneous scans queue behind each other. Postgres
enables truly parallel scanner workers.

**Add Alembic migrations.** The current `ALTER TABLE` approach in `init_db()`
works but doesn't track migration history. Alembic provides reversible,
version-controlled schema changes.

**Extract scanner into a task queue.** Replace `asyncio.create_task()` with
Celery/ARQ/Dramatiq. Benefits: retries with backoff, dead letter queues,
separate worker scaling, visibility into task state.

### Medium-term (3-6 months)

**Add a caching layer.** The main page query hits the DB on every request.
A Redis cache with 5-minute TTL would eliminate redundant queries. Invalidate
on scan completion.

**Move to server-sent events for scan progress.** Currently the UI has no
feedback during long scans. SSE would allow live progress without polling.

**Implement rate limiting per source.** Some sources (BS, BD) are high-traffic
APIs. Adding per-source rate limits and backoff prevents being blocked.

### Long-term (6-12 months)

**Separate scraper from web app.** Deploy scrapers as scheduled cloud functions
(AWS Lambda / Cloud Run Jobs) writing to a shared database. Web app becomes
a thin read-only API + frontend.

**Add user accounts for personalisation.** Saved filters, favourite venues,
watchlist notifications. Requires auth layer (OAuth2 / magic links).

**Full-text search.** SQLite FTS5 or Postgres tsvector for searching event
names, classes, and descriptions beyond exact-match filters.
