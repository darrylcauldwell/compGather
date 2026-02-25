"""Prometheus metrics for CompGather (EquiCalendar).

All custom metrics use the 'compgather_' prefix to avoid conflicts
with other applications in a shared observability stack.
"""

try:
    from prometheus_client import Counter, Gauge, Histogram, Info
except ImportError:
    # Provide no-op stubs so the app (and tests) still work without
    # prometheus_client installed (e.g. local venv outside Docker).
    class _NoOpMetric:
        """Stub that silently accepts any call."""
        def __init__(self, *a, **kw): pass
        def __getattr__(self, _): return lambda *a, **kw: self
    Counter = Gauge = Histogram = Info = _NoOpMetric

# Application info
APP_INFO = Info(
    "compgather_app",
    "CompGather application info"
)
APP_INFO.info({"version": "1.0.0", "name": "equicalendar"})

# Scan metrics
SCAN_DURATION_SECONDS = Histogram(
    "compgather_scan_duration_seconds",
    "Duration of source scans in seconds",
    ["source_name", "parser_key"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

SCAN_TOTAL = Counter(
    "compgather_scans_total",
    "Total number of scans by status",
    ["source_name", "status"],  # status: completed, failed
)

SCAN_COMPETITIONS_FOUND = Gauge(
    "compgather_scan_competitions_found",
    "Number of competitions found in last scan",
    ["source_name"],
)

# Venue metrics
VENUE_MATCH_TOTAL = Counter(
    "compgather_venue_matches_total",
    "Venue match outcomes by type",
    ["match_type"],  # alias, prefix, postcode, new, fuzzy, etc.
)

VENUES_TOTAL = Gauge(
    "compgather_venues_total",
    "Total number of venues",
    ["source"],  # seed_data, dynamic
)

VENUES_WITH_COORDS = Gauge(
    "compgather_venues_with_coordinates",
    "Number of venues that have been geocoded",
)

# Competition metrics
COMPETITIONS_ACTIVE = Gauge(
    "compgather_competitions_active",
    "Number of active future competitions",
)

COMPETITIONS_BY_DISCIPLINE = Gauge(
    "compgather_competitions_by_discipline",
    "Competition count by discipline",
    ["discipline"],
)

# Data quality
SOURCES_ENABLED = Gauge(
    "compgather_sources_enabled",
    "Number of enabled sources",
)

PARSER_ERRORS_TOTAL = Counter(
    "compgather_parser_errors_total",
    "Parser errors by source",
    ["source_name", "error_type"],
)

# Scheduler
SCHEDULER_LAST_RUN = Gauge(
    "compgather_scheduler_last_run_timestamp",
    "Unix timestamp of last scheduled scan run",
)
