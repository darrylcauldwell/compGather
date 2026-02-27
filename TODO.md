# EquiCalendar Todo List

## Completed (Latest Session - Feb 24, 2026)

- ✅ **Pony Club Parser Enhancement Plan** (6 phases completed)
  - Fixed PonyClubParser to accept entrymaster URLs
  - Extract postcodes from branch calendars
  - Clean up bad event names
  - All phases implemented and integrated

---

## Active Todo Items

### 1. Prepare App for meWeb Co-Hosting

**Status**: Planned, not started

**Context**: Prepare for deployment on shared meWeb platform with integrated observability

**What this means**:
1. **Observability Integration**:
   - Link to meWeb's existing Prometheus/Grafana/Loki
   - Stop running separate monitoring stack in production
   - Send metrics/logs to meWeb central observability

2. **Environment-Specific UI**:
   - **Dev**: Full navbar (Events, Venues, Classifier, Observability, Scrape) + all APIs + admin routes
   - **Production**: Events view only, no navbar, no admin routes, no clutter

**Benefits**:
- Clean user experience in production
- Infrastructure reuse (no duplicate monitoring)
- Easy multi-tenant deployment
- Clear dev vs production separation

**Implementation**:
- Add ENVIRONMENT config (dev/production)
- Conditional router registration in main.py
- Conditional navbar in templates
- Update docker-compose for meWeb integration
- Integration with meWeb observability endpoints

**Effort**: ~2 days

**Files**: config.py, main.py, base.html, docker-compose files

---

### 2. Pony Badge Semantics Design

**Status**: Deferred, awaiting design discussion

**Issue**: What should the "Pony" badge mean?
- Current semantics: "has dedicated pony classes"
- Problem: Training clinics "open to all" don't show as pony-suitable
- Options: Keep strict / Add "pony-friendly" tag / Create separate badges

**Action**: Schedule design discussion session to decide on semantics and implementation approach

**Example case**: Maddy Moffet Training Clinic (open to all, suitable for ponies, but no dedicated pony classes)

---

### 3. Map View

**Status**: Planned, not started

**User story**: "I want to see competitions on a map so I can spot clusters near me."

**Approach**:
- Add `/map` route with Leaflet.js map
- Plot events as markers using existing latitude/longitude
- Cluster markers at low zoom
- Click marker for event details
- Respect current filters

**Effort**: ~1 day (frontend-only, no backend work needed)

---

### 4. Structured Logging for Production

**Status**: Planned, not started

**Goal**: Machine-parseable logs for production log aggregation

**What to implement**:
- JSON structured logging (via `python-json-logger`)
- Key fields: timestamp, level, logger_name, source_id, parser_key, competitions_found, duration
- Integrate with Loki for log aggregation
- Update Grafana dashboards to query logs

**Why**: Currently using human-readable format; structured JSON enables ELK/Loki integration, better alerting

**Effort**: Medium (~1 day)

---

### 5. Parser Health Monitoring

**Status**: Planned, not started

**Goal**: Detect when a parser breaks (stops returning events or drops significantly)

**What to implement**:
- Track `competitions_found` per source per scan
- Alert if count drops >50% vs. previous scan
- Alert if count is 0 (likely parser failure)
- Add `/api/health/parsers` endpoint showing status per source
- Show trend sparklines on sources page
- Future: Slack/email notifications

**Why**: Parser breakage (HTML structure changes, URL changes) is silent without monitoring

**Effort**: Small (~4 hours for basic alerts; more for notifications)

---

## Discarded (Not Pursuing)

- Bookmarkable Filters (partial implementation exists, nice-to-have)
- Multi-Event Calendar Export (minor feature)
- Stale Event Detection (minor feature)
- Event Detail Pages (nice-to-have)
- Push Notifications (large effort, not prioritized)
- Cross-source Deduplication (architectural, not prioritized)
- Per-source Rate Limiting (advanced feature)
- Parser Smoke Tests in CI (would be nice, not critical)
- All other Roadmap Priority 2-3 items

---

## How to Use This List

1. Pick an item when ready to work on it
2. Update status to "In Progress"
3. Create a git branch for the work
4. Update this file when items are completed
5. Document any new decisions/constraints as you work

---

**Last updated**: Feb 24, 2026
**Session**: Complete Parser Refactoring + UI Overhaul
