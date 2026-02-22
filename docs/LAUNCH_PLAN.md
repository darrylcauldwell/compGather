# 30-Day Launch Plan

> From current state to public MVP. Assumes part-time effort (~2 hours/day).

---

## Week 1: Harden & Test (Days 1-7)

| Day | Task | Deliverable |
|-----|------|-------------|
| 1 | Add database indexes for main query columns | `idx_comp_date_active`, `idx_comp_discipline`, `idx_comp_venue` |
| 2 | Add parser fixture tests: save sample HTML for 5 highest-volume parsers (BS, Equipe, HorseMonkey, PC, BE), write happy-path tests | 5 new test files |
| 3 | Add API endpoint tests: competitions list, pagination, filters, iCal | `tests/test_api_competitions.py` |
| 4 | Add URL validation in scanner (reject non-http schemes) | Security hardening |
| 5 | Add scan threshold alerting: log warning if count <50% of previous | `app/services/scanner.py` |
| 6 | Set up `ruff` linter + `ruff.toml` config | Code quality baseline |
| 7 | Buffer / fix anything broken from days 1-6 | Clean green test suite |

**Exit criteria**: `pytest` passes, `ruff check` clean, all 26 parsers return data.

---

## Week 2: Polish & Features (Days 8-14)

| Day | Task | Deliverable |
|-----|------|-------------|
| 8-9 | Map view: add `/map` route with Leaflet.js, marker clusters, filter integration | New page |
| 10 | Multi-event calendar export: "Export Page" button | Bulk .ics download |
| 11 | "Copy Link" button for current filter state | Shareable URLs |
| 12 | Event detail page: `GET /competitions/{id}` with map pin + JSON-LD | SEO-ready detail pages |
| 13 | Mobile responsiveness audit: test on iPhone SE / small screen | CSS fixes |
| 14 | Buffer / polish | UI consistency pass |

**Exit criteria**: Core user journey works on mobile. Map view loads. Links are shareable.

---

## Week 3: Ops & Deployment (Days 15-21)

| Day | Task | Deliverable |
|-----|------|-------------|
| 15 | GitHub Actions CI: pytest + ruff + docker build on push | `.github/workflows/ci.yml` |
| 16 | Set up production server (VPS / Fly.io / Railway) | Running instance |
| 17 | Configure `docker-compose.prod.yml`: proper logging, restart policy, backup cron | Production compose |
| 18 | Add basic auth to write endpoints (`/api/sources`, `/api/scans`) | API key middleware |
| 19 | Add database backup script (daily cron, copy to host or S3) | `scripts/backup.sh` |
| 20 | Load test: verify page loads <500ms with 10K competitions | Performance baseline |
| 21 | Buffer / fix deployment issues | Stable production |

**Exit criteria**: App running on production URL. CI pipeline green. Backups automated.

---

## Week 4: Launch & Iterate (Days 22-30)

| Day | Task | Deliverable |
|-----|------|-------------|
| 22 | Write README.md (already created) | Public repo ready |
| 23 | Add CONTRIBUTING.md with parser development guide | Contributor onboarding |
| 24 | Initial public push to GitHub | Repo live |
| 25 | Share with 3-5 equestrian community contacts for feedback | User testing |
| 26-27 | Fix top 3 issues from user feedback | Iteration |
| 28 | Add Google Analytics or Plausible for usage tracking | Metrics |
| 29 | Post to equestrian forums / Facebook groups | Launch announcement |
| 30 | Review metrics, plan next sprint | Retrospective |

**Exit criteria**: Public URL shared. Real users accessing the site. Feedback loop established.

---

## Risk Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Parser breaks during launch week | High | Medium | Monitor scan logs daily; have generic LLM fallback |
| Source site blocks our IP | Medium | High | Use rotating delays; contact site owners proactively |
| SQLite performance at 10K+ rows | Low | Medium | Already paginated; add indexes in Week 1 |
| Zero user adoption | Medium | High | Validate with equestrian contacts before public launch |
| Copyright concerns from source sites | Low | High | Aggregate metadata only (name, date, venue); link back to source |

---

## Success Metrics (Day 30)

| Metric | Target |
|--------|--------|
| Parsers operational | 24/26 (>90%) |
| Page load time (p95) | <500ms |
| Unique visitors (first week) | >50 |
| Daily active users | >10 |
| Competitions in database | >7,000 |
| Distinct venues with coordinates | >500 |
| Test coverage | >60% on core modules |
