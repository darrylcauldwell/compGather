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

## Coding Rules

- **Docker**: port 8000 inside container → **host port 8001**. All curl examples use `localhost:8001`.
- **Parsers**: extend `BaseParser`, register with `@register_parser("key")`, import in `app/parsers/__init__.py`.
- **Parser output**: `list[ExtractedCompetition]` — see `app/schemas.py`.
- **Dedup key**: `(source_id, name, date_start, venue_name)` — name must match exactly.
- **Venue names**: always pass through `normalise_venue_name()` before storing.
- **Disciplines**: always pass through `normalise_discipline()` before storing. Returns `(canonical, is_competition)`.
- **Coordinates**: parsers can provide `latitude`/`longitude` directly; otherwise scanner geocodes from postcode.
- **Migrations**: SQLite — use `ALTER TABLE` with try/except in `app/database.py:init_db()`. No Alembic yet.
- **Tests**: run with `pytest`. Scanner tests use in-memory SQLite. Mock external HTTP calls.
- **Build**: `docker compose up -d --build` from project root.
