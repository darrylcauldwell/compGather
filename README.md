# EquiCalendar

A unified calendar for UK equestrian competitions. Aggregates events from 26 sources into a single searchable, sortable, filterable view with distance calculations from your postcode.

## The Problem

UK equestrian competitions are scattered across dozens of websites: British Showjumping, British Eventing, British Dressage, Pony Club branches, individual venue sites, and third-party listing platforms. Planning a competition season means checking 10+ sites, cross-referencing dates, and manually working out travel distances.

## The Solution

EquiCalendar scrapes all major UK equestrian listing sites daily, normalises the data (venue names, disciplines, postcodes), calculates distances from your home postcode, and presents everything in one paginated table with filters and calendar export.

## Features

- **26 source parsers** covering national federations, venue sites, and aggregators
- **Discipline normalisation** — 46 raw categories mapped to 15 canonical types
- **Venue normalisation** — consistent naming across all sources
- **Distance from home** — haversine calculation from your postcode
- **Pagination** — 50 results per page (no more 11MB pages)
- **Column sorting** — date, name, discipline, venue, distance
- **Inline filters** — discipline, venue (searchable), pony classes, date range, max distance
- **iCalendar export** — download any event as a .ics file for Apple Calendar / Google Calendar
- **Non-competition filtering** — arena hire and training sessions hidden by default
- **Dark/light theme** — defaults to dark, toggle in header
- **Scheduled daily scans** — automatic data refresh at 06:00
- **Source management UI** — add/edit/delete sources, trigger manual scans

## Quick Start

```bash
# Clone
git clone https://github.com/darrylcauldwell/compGather.git
cd compGather

# Start (builds Docker image with all dependencies)
docker compose up -d --build

# Open in browser
open http://localhost:8001
```

The app starts with an empty database. Add sources via the Sources page or seed them:

```bash
# Trigger a scan of all enabled sources
curl -X POST http://localhost:8001/api/scans -H "Content-Type: application/json" -d '{}'
```

## Configuration

Environment variables (set in `docker-compose.yml` or `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `HOME_POSTCODE` | `SW1A 1AA` | Your home postcode for distance calculations |
| `SCAN_SCHEDULE` | `06:00` | Daily scan time (HH:MM, 24hr) |
| `LOG_LEVEL` | `INFO` | Python log level |
| `OLLAMA_URL` | `http://host.docker.internal:11434` | Ollama URL for generic LLM parser |
| `OLLAMA_MODEL` | `qwen2.5:1.5b` | Ollama model name |

## Architecture

```
Source Sites (26)
      |
      v
   Parsers (per-source scraping logic)
      |
      v
   Scanner (normalise venues + disciplines, geocode, dedup, upsert)
      |
      v
   SQLite Database
      |
      +---> HTML pages (Jinja2 + Tailwind CSS)
      +---> REST API (/api/competitions, /api/sources, /api/scans)
      +---> iCal export (/api/competitions/{id}/ical)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full details.

## Supported Sources

| Source | Parser | Type |
|--------|--------|------|
| British Showjumping | `british_showjumping` | HTML pagination |
| British Eventing | `british_eventing` | HTML search |
| British Dressage | `british_dressage` | JSON API |
| The Pony Club | `pony_club` | HTML + branch pages |
| Equipe Online | `equipe_online` | JSON API (GBR events) |
| Horse Monkey | `horse_monkey` | JSON search API |
| Horse Events | `horse_events` | Sitemap crawling |
| NSEA | `nsea` | HTML pagination |
| BSPS | `bsps` | Calendar with postcodes |
| BSHA | `bsha` | HTML listings |
| My Riding Life | `my_riding_life` | Playwright (ASP.NET postback) |
| Horsevents | `horsevents` | HTML listings |
| Equo Events | `equo_events` | HTML listings |
| Equilive | `equilive` | HTML listings |
| Arena UK | `arena_uk` | HTML listings |
| Outdoor Shows | `outdoor_shows` | Sitemap crawling |
| ASAO | `asao` | WordPress AJAX (Search Filter Pro) |
| Ashwood | `ashwood` | WordPress MEC plugin |
| Derby College | `derby_college` | .docx file parsing |
| Addington | `addington` | Events API |
| Hickstead | `hickstead` | Fixed venue |
| Epworth | `epworth` | Fixed venue |
| NVEC | `nvec` | Fixed venue |
| Showground | `showground` | Fixed venue |
| Kelsall Hill | `kelsall_hill` | Fixed venue |
| Generic (LLM) | `generic` | Ollama-based extraction |

## API

```bash
# List competitions (JSON)
curl http://localhost:8001/api/competitions

# Filter by date and distance
curl "http://localhost:8001/api/competitions?date_from=2026-03-01&max_distance=50"

# Download iCal for a specific event
curl http://localhost:8001/api/competitions/72/ical -o event.ics

# Trigger scan for all sources
curl -X POST http://localhost:8001/api/scans -H "Content-Type: application/json" -d '{}'

# Trigger scan for a specific source
curl -X POST http://localhost:8001/api/scans -H "Content-Type: application/json" -d '{"source_id": 1}'

# Update home postcode
curl -X POST http://localhost:8001/api/competitions/update-postcode \
  -H "Content-Type: application/json" -d '{"postcode": "DE45 1BS"}'
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2.0 (async) |
| Database | SQLite via aiosqlite |
| Frontend | Jinja2 templates, Tailwind CSS 4 |
| Browser automation | Playwright (for JS-rendered sites) |
| Geocoding | postcodes.io + Nominatim |
| Scheduling | APScheduler |
| LLM fallback | Ollama (qwen2.5:1.5b) |
| Container | Docker multi-stage (Node + Python) |

## Development

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Node dependencies (for CSS)
npm install

# Watch CSS changes
npm run watch:css

# Run tests
pytest

# Run app locally (without Docker)
uvicorn app.main:app --reload --port 8000
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — system design, data models, data flow
- [Feature Roadmap](docs/ROADMAP.md) — planned features with implementation approaches
- [Best Practices Audit](docs/BEST_PRACTICES.md) — pitfalls and mitigations
- [Launch Plan](docs/LAUNCH_PLAN.md) — 30-day plan from current state to public MVP

## License

MIT
