# EquiCalendar — Project Instructions

## Documentation (read on-demand)

| Doc | When to read | Path |
|-----|-------------|------|
| Architecture | Before any structural change | `docs/ARCHITECTURE.md` |
| Feature Roadmap | When picking what to build next | `docs/ROADMAP.md` |
| Best Practices | Before adding parsers, changing DB, or security work | `docs/BEST_PRACTICES.md` |
| Launch Plan | For sprint context and success metrics | `docs/LAUNCH_PLAN.md` |

## Completed: Week 1 — Harden & Test

- [x] Database indexes: `idx_comp_date_active`, `idx_comp_discipline`, `idx_comp_venue`
- [x] Parser fixture tests for top 5 parsers (12 tests in `tests/test_parsers.py`)
- [x] API endpoint tests (12 tests in `tests/test_api_competitions.py`)
- [x] URL validation in scanner
- [x] Scan threshold alerting
- [x] Ruff linter with `ruff.toml`

## Completed: Week 2 — Polish & Features

- [x] Map view: `/map` with Leaflet.js, MarkerCluster, dark/light tiles, filter bar
- [x] Multi-event calendar export: "Export .ics" button, `GET /api/competitions/export-ical`
- [x] "Copy Link" button with clipboard API + "Copied!" feedback
- [x] Event detail page: `/competitions/{id}` with mini map + JSON-LD (schema.org Event)
- [x] Mobile responsiveness: hidden columns on small screens, larger touch targets

## Completed: Week 3 — Ops & Deployment

- [x] GitHub Actions CI: `.github/workflows/ci.yml` (lint → test → docker build)
- [x] Production docker-compose: `docker-compose.prod.yml` (restart, logging, resource limits)
- [x] API key auth on write endpoints (`X-API-Key` header, `API_KEY` env var)
- [x] Database backup script: `scripts/backup.sh` (7-day rotation)
- [ ] Set up production server (requires hosting provider choice)
- [ ] Load test: verify page loads <500ms with 10K competitions

## Completed: Week 4 — Launch & Growth

- [x] CONTRIBUTING.md with parser development guide
- [x] Plausible analytics integration (`ANALYTICS_DOMAIN` env var, conditional `<script>` in base.html)
- [ ] User testing (manual)
- [ ] Forum/community posting

## Completed: Data Quality & Resilience

- [x] Source auto-seeding: `_SOURCE_DEFS` in scanner.py, `seed_sources()` on startup
- [x] Venue matching pipeline: `VenueMatcher` with alias → prefix → postcode → new
- [x] Venue normalisation: iterative suffix stripping, 170+ aliases, address truncation, junk guards
- [x] Postcode normalisation: `normalise_postcode()` at all ingest points
- [x] Admin view: hidden `/admin` page (no nav link), scan triggers only
- [x] Data resilience: full destroy → rebuild → rescan recovers all data
- [x] British Dressage seed: JSON fallback when BD API is down
- [x] Fixed broken parsers: Abbey Farm (REST API), Derby College (new URL), Epworth (table parsing), NVEC (Playwright SPA)

## Coding Rules

- **Docker**: port 8000 inside container → **host port 8001**. All curl examples use `localhost:8001`.
- **Parsers**: extend `BaseParser`, register with `@register_parser("key")`, import in `app/parsers/__init__.py`.
- **Parser output**: `list[ExtractedCompetition]` — see `app/schemas.py`.
- **Dedup key**: `(source_id, name, date_start, venue_id)` — name must match exactly.
- **Venue names**: always pass through `normalise_venue_name()` before storing. Guards reject URLs, postcodes, very long strings.
- **Venue seed data**: all venue postcodes, coordinates, aliases, and ambiguous names live in `app/venue_seeds.json`. Loaded via `app/seed_data.py` (`get_venue_seeds()`, `get_venue_aliases()`, `get_ambiguous_names()`).
- **Venue aliases**: add to the venue's `"aliases"` array in `app/venue_seeds.json`, rebuild, then run `scripts/renormalise_venues.py`.
- **Postcodes**: always pass through `normalise_postcode()` before storing.
- **Disciplines**: always pass through `normalise_discipline()` before storing. Returns `(canonical, is_competition)`.
- **Sources**: defined in `_SOURCE_DEFS` in `scanner.py`. Auto-seeded on startup. No runtime creation needed.
- **Admin UI**: hidden at `/admin` — no nav link, scan triggers only, no disable/delete.
- **Venue FK**: Competition has `venue_id` FK → venues table. Venue data (name, postcode, coords, distance) lives on Venue; Competition has `@property` accessors that delegate to `self.venue`. Always eager-load venue (`selectinload` or `contains_eager` with join) before accessing venue properties.
- **Coordinates**: parsers can provide `latitude`/`longitude` directly; scanner's `_ensure_venue_coords()` geocodes onto the Venue row.
- **Distance**: `distance_miles` lives on Venue (~670 rows), not Competition (~7000 rows). Changing home postcode recalculates on venues only.
- **Migrations**: SQLite — use `ALTER TABLE` with try/except in `app/database.py:init_db()`. No Alembic yet.
- **Tests**: run with `pytest`. Scanner tests use in-memory SQLite. Mock external HTTP calls.
- **Build**: `docker compose up -d --build` from project root.
