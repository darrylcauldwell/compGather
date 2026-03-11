"""Prometheus metrics for EquiCalendar.

All custom metrics use the 'equicalendar_' prefix to avoid conflicts
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
    "equicalendar_app",
    "EquiCalendar application info"
)
APP_INFO.info({"version": "1.0.0", "name": "equicalendar"})

# Scan metrics
SCAN_DURATION_SECONDS = Histogram(
    "equicalendar_scan_duration_seconds",
    "Duration of source scans in seconds",
    ["source_name", "parser_key"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

SCAN_TOTAL = Counter(
    "equicalendar_scans_total",
    "Total number of scans by status",
    ["source_name", "status"],  # status: completed, failed
)

SCAN_COMPETITIONS_FOUND = Gauge(
    "equicalendar_scan_competitions_found",
    "Number of competitions found in last scan",
    ["source_name"],
)

# Venue metrics
VENUE_MATCH_TOTAL = Counter(
    "equicalendar_venue_matches_total",
    "Venue match outcomes by type",
    ["match_type"],  # alias, prefix, postcode, new, fuzzy, etc.
)

VENUES_TOTAL = Gauge(
    "equicalendar_venues_total",
    "Total number of venues",
    ["source"],  # seed_data, dynamic
)

VENUES_WITH_COORDS = Gauge(
    "equicalendar_venues_with_coordinates",
    "Number of venues that have been geocoded",
)

# Competition metrics
COMPETITIONS_ACTIVE = Gauge(
    "equicalendar_competitions_active",
    "Number of active future competitions",
)

COMPETITIONS_BY_DISCIPLINE = Gauge(
    "equicalendar_competitions_by_discipline",
    "Competition count by discipline",
    ["discipline"],
)

# Data quality
SOURCES_ENABLED = Gauge(
    "equicalendar_sources_enabled",
    "Number of enabled sources",
)

PARSER_ERRORS_TOTAL = Counter(
    "equicalendar_parser_errors_total",
    "Parser errors by source",
    ["source_name", "error_type"],
)

# Scheduler
SCHEDULER_LAST_RUN = Gauge(
    "equicalendar_scheduler_last_run_timestamp",
    "Unix timestamp of last scheduled scan run",
)
