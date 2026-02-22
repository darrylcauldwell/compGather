# EquiCalendar Feature Roadmap

> Planned features ranked by user impact, with implementation approaches.

---

## Implemented (Current State)

| Feature | Status | Notes |
|---------|--------|-------|
| 26 source parsers | Done | BS, BE, BD, PC, HorseMonkey, Equipe, NSEA, etc. |
| Venue normalisation | Done | Suffix stripping, alias mapping, title-casing |
| Discipline normalisation | Done | 70+ raw values mapped to 15 canonical categories |
| Non-competition filtering | Done | Venue hire + training hidden by default via `is_competition` |
| Geocoding + distance | Done | postcodes.io + Nominatim, haversine from home postcode |
| Paginated table (50/page) | Done | Down from 11.8MB to ~230KB per page |
| Column sorting | Done | Date, name, discipline, venue, distance |
| Inline filter dropdowns | Done | Discipline, venue (with search), pony classes |
| iCalendar export | Done | Per-event .ics download with VEVENT |
| Scheduled daily scans | Done | APScheduler cron at 06:00 |
| Dark/light theme | Done | CSS custom properties, localStorage persistence |
| Source management UI | Done | Add/edit/delete sources, trigger scans |

---

## Priority 1: Core Experience (Next)

### 1.1 Map View

**User story**: "I want to see competitions on a map so I can spot clusters near me."

**Approach**:
- Add a `/map` route serving a Leaflet.js map
- Plot competitions as markers using existing `latitude`/`longitude`
- Cluster markers at low zoom levels (Leaflet.markercluster)
- Click marker to show event name, date, discipline, distance
- Respect current filters (date range, discipline, distance)
- No new backend work needed; reuse existing API endpoint

**Effort**: Small. Frontend-only. ~1 day.

### 1.2 Saved Filters / Bookmarkable URLs

**User story**: "I want to share my filtered view (Dressage within 50 miles) as a link."

**Approach**:
- Already partially working: filters are URL params (`?discipline=Dressage&max_distance=50`)
- Add a "Copy Link" button that copies current URL to clipboard
- Add browser history push so back/forward works correctly
- Add "Save as default" that stores filter set in localStorage

**Effort**: Tiny. Frontend-only. ~2 hours.

### 1.3 Multi-Event Calendar Export

**User story**: "I want to download a whole page of results as one calendar file."

**Approach**:
- Add "Export Page to Calendar" button below the table
- `GET /api/competitions/ical?date_from=...&discipline=...` returns multi-VEVENT .ics
- Reuse existing filter logic from the page query
- Single file with all 50 events from current page

**Effort**: Small. Extend existing ical endpoint. ~3 hours.

---

## Priority 2: Data Quality

### 2.1 Venue Deduplication Dashboard

**User story**: "As a maintainer, I want to see likely duplicate venues and merge them."

**Approach**:
- Add `/admin/venues` page showing venues with similar names (Levenshtein distance < 3)
- Group candidates: "Eland Lodge" vs "Eland Lodge Equestrian" vs "Eland Lodge EC"
- One-click merge: update all competition records to the canonical name
- Log merges for audit trail

**Effort**: Medium. New page + merge logic. ~1 day.

### 2.2 Stale Event Detection

**User story**: "Events that were last seen 30+ days ago are probably cancelled."

**Approach**:
- Add a `status` column to Competition: `active`, `stale`, `removed`
- If `last_seen_at` < 30 days ago and event is in the future, mark as `stale`
- Show stale events with a visual indicator (faded row, warning badge)
- Run as part of the daily scheduled job

**Effort**: Small. Migration + scheduled task. ~4 hours.

### 2.3 Parser Health Monitoring

**User story**: "I want to know immediately when a parser breaks."

**Approach**:
- Track `competitions_found` per scan; alert if count drops >50% vs. previous
- Add a `/api/health/parsers` endpoint showing last scan status per source
- Sources page already shows scan history; add trend sparkline
- Future: webhook notification (Slack/email) on parser failure

**Effort**: Small. Query logic + UI. ~4 hours.

---

## Priority 3: User Engagement

### 3.1 Event Detail Pages

**User story**: "I want to see all details about an event before deciding to enter."

**Approach**:
- Add `GET /competitions/{id}` HTML page
- Show: full name, dates, venue with map pin, discipline, source link, iCal button
- Link from the table row (click event name)
- Structured data (JSON-LD Event) for search engine indexing

**Effort**: Small. New template + route. ~4 hours.

### 3.2 "Near Me" with Browser Geolocation

**User story**: "I want to use my phone's GPS instead of typing a postcode."

**Approach**:
- Add a "Use my location" button next to the postcode field
- `navigator.geolocation.getCurrentPosition()` -> reverse geocode to postcode
- Or calculate distances directly from GPS coords (skip postcode entirely)
- Store preference in localStorage

**Effort**: Small. Frontend + minor API change. ~3 hours.

### 3.3 Push Notifications (New Events)

**User story**: "Notify me when a new event is added within 50 miles."

**Approach**:
- Requires user accounts (email at minimum)
- After each scan, diff new vs. existing competitions
- Match new events against each user's saved filter criteria
- Send email digest (daily) or web push notification
- Start with email; add web push later

**Effort**: Large. Auth + notification system. ~1 week.

---

## Priority 4: Scale & Operations

### 4.1 PostgreSQL Migration

**Why**: SQLite write lock limits concurrent scan workers.

**Approach**:
- Replace `sqlite+aiosqlite` with `postgresql+asyncpg` in config
- Add Alembic for schema migrations
- Use `docker compose` to add a Postgres container
- Data migration: `sqlite3 .dump` -> psql import

**Effort**: Medium. ~1 day including testing.

### 4.2 Background Task Queue

**Why**: `asyncio.create_task()` loses tasks on restart; no retries or backoff.

**Approach**:
- Add ARQ (async Redis queue) or Celery
- Scanner becomes a worker consuming from a queue
- Scheduler enqueues jobs instead of running them directly
- Adds: retries, timeouts, dead letter queue, task visibility

**Effort**: Medium. ~1 day.

### 4.3 CI/CD Pipeline

**Approach**:
- GitHub Actions workflow:
  - `pytest` on push (in-memory SQLite)
  - `ruff check` for linting
  - Docker build test
  - Deploy to VPS on merge to `main` (docker compose pull + up)
- Add `ruff.toml` and pre-commit hooks

**Effort**: Small. ~3 hours.

### 4.4 Monitoring & Alerting

**Approach**:
- Prometheus metrics endpoint (`/metrics`) via `prometheus-fastapi-instrumentator`
- Key metrics: request latency, scan duration, competitions per scan, error rate
- Grafana dashboard for visualisation
- Alert on: scan failure, zero competitions found, response time > 2s

**Effort**: Medium. ~1 day.

---

## Backlog (Ideas)

| Feature | Notes |
|---------|-------|
| **Entry system integration** | Deep link to Entrymaster/HorseEvents/BS entry pages |
| **Class-level detail** | Parse individual classes (heights, age groups) where available |
| **Historical data** | Track past results; "events I've attended" diary |
| **Venue reviews** | User-submitted venue ratings (facilities, surface quality) |
| **Weather overlay** | Show forecast for event dates/locations |
| **Mobile app** | PWA wrapper or React Native; push notifications |
| **Public API** | Rate-limited API for third-party integrations |
| **Affiliate revenue** | Partner links to accommodation, transport near venues |
