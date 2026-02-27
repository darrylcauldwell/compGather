# Refactoring Fixes Needed: Specific Code Changes Required

## Overview

This document lists the exact code changes needed to complete the refactoring. All changes are straightforward: remove date-filtering imports and checks.

---

## Priority 1: Partially Refactored Parsers (Phase 4A needed)

These 9 parsers have Phase 4B done but Phase 4A skipped. They still filter out past events.

### 1. addington.py

**File:** `/Users/darrylcauldwell/Library/Mobile Documents/com~apple~CloudDocs/Development/compGather/app/parsers/addington.py`

**Line 13 - Remove import:**
```python
# BEFORE:
from app.parsers.utils import (
    detect_pony_classes,
    is_future_event,  # ← REMOVE THIS LINE
)

# AFTER:
from app.parsers.utils import (
    detect_pony_classes,
)
```

**Line 50 - Remove API parameter:**
```python
# BEFORE:
params = {
    "per_page": PER_PAGE,
    "start_date": today,  # ← REMOVE THIS LINE
}

# AFTER:
params = {
    "per_page": PER_PAGE,
}
```

**Lines 96-97 - Remove filtering check:**
```python
# BEFORE:
if not is_future_event(date_start, date_end):  # ← REMOVE THESE 2 LINES
    return None

# AFTER:
# (no change needed, just remove the if block)
```

---

### 2. arena_uk.py

**File:** `/Users/darrylcauldwell/Library/Mobile Documents/com~apple~CloudDocs/Development/compGather/app/parsers/arena_uk.py`

**Line 14 - Remove import:**
```python
# BEFORE:
from app.parsers.utils import (
    detect_pony_classes,
    is_future_event,  # ← REMOVE THIS LINE
)

# AFTER:
from app.parsers.utils import (
    detect_pony_classes,
)
```

**Line 194 - Remove filtering check:**
```python
# BEFORE:
if not is_future_event(date_start, date_end):  # ← REMOVE THESE 2 LINES
    return None

# AFTER:
# (no change needed, just remove the if block)
```

---

### 3. ashwood.py

**File:** `/Users/darrylcauldwell/Library/Mobile Documents/com~apple~CloudDocs/Development/compGather/app/parsers/ashwood.py`

**Line 14 - Remove import:**
```python
# BEFORE:
from app.parsers.utils import (
    detect_pony_classes,
    is_future_event,  # ← REMOVE THIS LINE
)

# AFTER:
from app.parsers.utils import (
    detect_pony_classes,
)
```

**Lines 96-97 - Remove first filtering check (RSS parsing):**
```python
# BEFORE:
if not is_future_event(date_start, date_end):  # ← REMOVE THESE 2 LINES
    continue

# AFTER:
# (no change needed, just remove the if block)
```

**Lines 214-215 - Remove second filtering check (Listing parsing):**
```python
# BEFORE:
if not is_future_event(date_start):  # ← REMOVE THESE 2 LINES
    return None

# AFTER:
# (no change needed, just remove the if block)
```

---

### 4. horsevents.py

**File:** `/Users/darrylcauldwell/Library/Mobile Documents/com~apple~CloudDocs/Development/compGather/app/parsers/horsevents.py`

**Line 14 - Remove import:**
```python
# BEFORE:
from app.parsers.utils import is_future_event  # ← REMOVE THIS LINE

# AFTER:
# (remove the entire line)
```

**Line 202 - Remove filtering check:**
```python
# BEFORE:
if not is_future_event(date_start, date_end):  # ← REMOVE THESE 2 LINES
    return None

# AFTER:
# (no change needed, just remove the if block)
```

---

### 5. my_riding_life.py

**File:** `/Users/darrylcauldwell/Library/Mobile Documents/com~apple~CloudDocs/Development/compGather/app/parsers/my_riding_life.py`

**Line 14 - Remove import:**
```python
# BEFORE:
from app.parsers.utils import (
    detect_pony_classes,
    is_future_event,  # ← REMOVE THIS LINE
)

# AFTER:
from app.parsers.utils import (
    detect_pony_classes,
)
```

**Lines 117-118 - Remove filtering check:**
```python
# BEFORE:
if not is_future_event(date_start, date_end):  # ← REMOVE THESE 2 LINES
    return None

# AFTER:
# (no change needed, just remove the if block)
```

---

### 6. pony_club.py

**File:** `/Users/darrylcauldwell/Library/Mobile Documents/com~apple~CloudDocs/Development/compGather/app/parsers/pony_club.py`

**Line 13 - Remove import:**
```python
# BEFORE:
from app.parsers.utils import extract_postcode, is_future_event  # ← REMOVE is_future_event

# AFTER:
from app.parsers.utils import extract_postcode
```

**Lines 148-149 - Remove filtering check:**
```python
# BEFORE:
if not is_future_event(date_start):  # ← REMOVE THESE 2 LINES
    return None

# AFTER:
# (no change needed, just remove the if block)
```

---

### 7. showground.py

**File:** `/Users/darrylcauldwell/Library/Mobile Documents/com~apple~CloudDocs/Development/compGather/app/parsers/showground.py`

**Line 14 - Remove import:**
```python
# BEFORE:
from app.parsers.utils import (
    detect_pony_classes,
    is_future_event,  # ← REMOVE THIS LINE
)

# AFTER:
from app.parsers.utils import (
    detect_pony_classes,
)
```

**Lines 120-121 - Remove filtering check:**
```python
# BEFORE:
if not is_future_event(date_start_str, date_end_str):  # ← REMOVE THESE 2 LINES
    continue

# AFTER:
# (no change needed, just remove the if block)
```

---

### 8. british_showjumping.py

**File:** `/Users/darrylcauldwell/Library/Mobile Documents/com~apple~CloudDocs/Development/compGather/app/parsers/british_showjumping.py`

**Line 13 - Remove import:**
```python
# BEFORE:
from app.parsers.utils import is_future_event  # ← REMOVE THIS LINE

# AFTER:
# (remove the entire line)
```

**Line 67 - Remove or invert filtering check:**
```python
# BEFORE:
if is_future_event(date_start, date_end):  # ← INVERT THIS (remove the check)
    # events are appended inside this if block

# AFTER:
# Move the event appending outside the if block
# (This one is inverted, so remove the if entirely)
```

---

### 9. equipe_online.py

**File:** `/Users/darrylcauldwell/Library/Mobile Documents/com~apple~CloudDocs/Development/compGather/app/parsers/equipe_online.py`

**Line 10 - Remove import:**
```python
# BEFORE:
from app.parsers.utils import infer_discipline, is_future_event  # ← REMOVE is_future_event

# AFTER:
from app.parsers.utils import infer_discipline
```

**Line 74 - Remove filtering check:**
```python
# BEFORE:
return is_future_event(meeting.get("start_on", ""), end_date)

# AFTER:
return True  # (always include, don't filter)
```

---

## Priority 2: Claimed But Untouched Parsers (Both phases needed)

These 5 parsers were explicitly listed as Phase 4A fixed but git diff shows zero changes.

### 1. brook_farm.py

**File:** `/Users/darrylcauldwell/Library/Mobile Documents/com~apple~CloudDocs/Development/compGather/app/parsers/brook_farm.py`

**Line 12 - Remove import:**
```python
from app.parsers.utils import detect_pony_classes, infer_discipline, is_future_event
# ↓
from app.parsers.utils import detect_pony_classes, infer_discipline
```

**Lines 112-113 - Remove filtering check:**
```python
if not is_future_event(date_start):
    return None
# Remove both lines
```

---

### 2. dean_valley.py

**File:** `/Users/darrylcauldwell/Library/Mobile Documents/com~apple~CloudDocs/Development/compGather/app/parsers/dean_valley.py`

**Line 12 - Remove import:**
```python
from app.parsers.utils import detect_pony_classes, infer_discipline, is_future_event
# ↓
from app.parsers.utils import detect_pony_classes, infer_discipline
```

**Lines 170-171 - Remove filtering check:**
```python
if not is_future_event(date_start):
    return None
# Remove both lines
```

---

### 3. hartpury.py

**File:** `/Users/darrylcauldwell/Library/Mobile Documents/com~apple~CloudDocs/Development/compGather/app/parsers/hartpury.py`

**Line 12 - Remove import:**
```python
from app.parsers.utils import detect_pony_classes, infer_discipline, is_future_event
# ↓
from app.parsers.utils import detect_pony_classes, infer_discipline
```

**Lines 130-131 - Remove filtering check:**
```python
if not is_future_event(date_start):
    return None
# Remove both lines
```

---

### 4. northallerton.py

**File:** `/Users/darrylcauldwell/Library/Mobile Documents/com~apple~CloudDocs/Development/compGather/app/parsers/northallerton.py`

**Line 12 - Remove import:**
```python
from app.parsers.utils import detect_pony_classes, infer_discipline, is_future_event
# ↓
from app.parsers.utils import detect_pony_classes, infer_discipline
```

**Lines 128-129 - Remove filtering check:**
```python
if not is_future_event(date_start):
    return None
# Remove both lines
```

---

### 5. port_royal.py

**File:** `/Users/darrylcauldwell/Library/Mobile Documents/com~apple~CloudDocs/Development/compGather/app/parsers/port_royal.py`

**Line 12 - Remove import:**
```python
from app.parsers.utils import detect_pony_classes, infer_discipline, is_future_event
# ↓
from app.parsers.utils import detect_pony_classes, infer_discipline
```

**Lines 106-107 - Remove filtering check:**
```python
if not is_future_event(date_start):
    return None
# Remove both lines
```

---

## Priority 3: Completely Untouched Parsers (Both phases needed)

### 1. solihull.py

**File:** `/Users/darrylcauldwell/Library/Mobile Documents/com~apple~CloudDocs/Development/compGather/app/parsers/solihull.py`

**Line 12 - Remove import:**
```python
from app.parsers.utils import detect_pony_classes, infer_discipline, is_future_event
# ↓
from app.parsers.utils import detect_pony_classes, infer_discipline
```

**Lines 111-112 - Remove filtering check:**
```python
if not is_future_event(date_start):
    return None
# Remove both lines
```

---

### 2. sykehouse.py

**File:** `/Users/darrylcauldwell/Library/Mobile Documents/com~apple~CloudDocs/Development/compGather/app/parsers/sykehouse.py`

**Line 12 - Remove import:**
```python
from app.parsers.utils import detect_pony_classes, infer_discipline, is_future_event
# ↓
from app.parsers.utils import detect_pony_classes, infer_discipline
```

**Lines 147-148 - Remove filtering check:**
```python
if not is_future_event(date_start):
    return None
# Remove both lines
```

---

### 3. horse_events.py (SPECIAL CASE - Most Complex)

**File:** `/Users/darrylcauldwell/Library/Mobile Documents/com~apple~CloudDocs/Development/compGather/app/parsers/horse_events.py`

**Line 14 - Remove classify_event import:**
```python
# BEFORE:
from app.parsers.utils import classify_event, extract_venue_from_name

# AFTER:
from app.parsers.utils import extract_venue_from_name
```

**Lines 232-234 - Remove classify_event call in rallies listing:**
```python
# BEFORE:
discipline, _ = classify_event(name)
if not discipline and "/pony-club-rallies/" in event_url:
    discipline = "Pony Club"

# AFTER:
# Discipline will be classified by EventClassifier
if "/pony-club-rallies/" in event_url:
    discipline = "Pony Club"
else:
    discipline = None
```

**Lines 347-349 - Remove classify_event call in detail pages:**
```python
# BEFORE:
discipline, _ = classify_event(name)
if not discipline and "/pony-club-rallies/" in url:
    discipline = "Pony Club"

# AFTER:
# Discipline will be classified by EventClassifier
if "/pony-club-rallies/" in url:
    discipline = "Pony Club"
else:
    discipline = None
```

**Lines 205-206 - Remove past event filtering in rallies listing:**
```python
# BEFORE:
if start_date < today:
    return None

# AFTER:
# Remove these lines entirely (extract all events)
```

**Lines 321-323 - Remove past event filtering in detail pages:**
```python
# BEFORE:
try:
    start_dt = date.fromisoformat(start_date_str)
    if start_dt < today:
        return None
except ValueError:
    pass

# AFTER:
try:
    start_dt = date.fromisoformat(start_date_str)
    # Remove the if statement, keep parsing
except ValueError:
    pass
```

**Lines 268-273 - Remove _is_future_url helper (or rename for future use):**
```python
# BEFORE:
def _is_future_url(self, url: str, today: date) -> bool:
    """Check if a URL's embedded date is in the future (or undetermined)."""
    d = _date_from_slug(url)
    if d is None:
        return True  # can't tell, include it
    return d >= today

# AND remove its usage at line 90:
detail_urls = [
    u for u in sitemap_urls
    if "/horse-events/" in u and self._is_future_url(u, today)  # ← Remove the _is_future_url check
]

# AFTER:
# Remove _is_future_url method entirely
# Update line 90:
detail_urls = [
    u for u in sitemap_urls
    if "/horse-events/" in u
]
```

---

## Summary of Changes Needed

| Priority | Parser | Changes | Complexity |
|----------|--------|---------|-----------|
| 1 | addington | 3 locations (import, API param, check) | Medium |
| 1 | arena_uk | 2 locations (import, check) | Low |
| 1 | ashwood | 3 locations (import, 2 checks) | Low |
| 1 | horsevents | 2 locations (import, check) | Low |
| 1 | my_riding_life | 2 locations (import, check) | Low |
| 1 | pony_club | 2 locations (import, check) | Low |
| 1 | showground | 2 locations (import, check) | Low |
| 1 | british_showjumping | 2 locations (import, inverted check) | Low |
| 1 | equipe_online | 2 locations (import, inverted return) | Low |
| 2 | brook_farm | 2 locations (import, check) | Low |
| 2 | dean_valley | 2 locations (import, check) | Low |
| 2 | hartpury | 2 locations (import, check) | Low |
| 2 | northallerton | 2 locations (import, check) | Low |
| 2 | port_royal | 2 locations (import, check) | Low |
| 3 | solihull | 2 locations (import, check) | Low |
| 3 | sykehouse | 2 locations (import, check) | Low |
| 3 | horse_events | 6 locations (import, 2 classify_event, 2 date checks, helper) | High |

**Total: 17 parsers, ~35 code locations, ~40 lines to remove**

All changes follow the same pattern:
1. Remove `is_future_event` or `classify_event` from imports
2. Remove the date-filtering or classification check
3. Optionally add comment about EventClassifier handling it

---

## Validation Checklist

After making changes, verify:

- [ ] All 17 parsers modified
- [ ] No syntax errors (run `python -m py_compile app/parsers/*.py`)
- [ ] Removed all `is_future_event` references (except in utils.py definition)
- [ ] Removed all `classify_event` references from parsers (except horse_events → EventClassifier)
- [ ] All imports cleaned up (no unused imports)
- [ ] Added comments where classification/filtering was removed
- [ ] Ran Docker build: `docker compose up -d --build`
- [ ] Ran scanner on test source: verify historical events extracted
- [ ] No data loss: verify event count increases after changes
