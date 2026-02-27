# Refactoring Patterns: Visual Summary

## Parser Refactoring Status Matrix

### Pattern 1: Completely Refactored ✓ (23 parsers)

Both `is_future_event()` and `classify_event()` removed from working tree. Ready to commit.

```
Working Tree:  is_future_event ❌ | classify_event ❌ | ExtractedEvent ⚠️
Committed:     is_future_event ✓  | classify_event ✓  | ExtractedCompetition ✓
Impact:        Full refactor done, just needs commit
```

**Parsers:** abbey_farm, asao, ballavartyn, british_dressage, british_eventing, british_horseball, bsha, bsps, derby_college, endurance_gb, entry_master, epworth, equilive, equo_events, hickstead, horse_monkey, hpa_polo, its_plain_sailing, kelsall_hill, morris, nsea, nvec, outdoor_shows

**Example Code (british_eventing.py):**
```python
# ✓ No date filtering
for tr in soup.find_all("tr"):
    # ... parse event ...
    competitions.append(ExtractedCompetition(...))  # All events extracted

# ✓ No classify_event call
# Discipline determined by EventClassifier in scanner
```

---

### Pattern 2: Partial Refactor - Phase 4B Only ⚠️ (9 parsers)

`classify_event()` removed but `is_future_event()` filtering still active. Needs Phase 4A completion.

```
Working Tree:  is_future_event ✓  | classify_event ❌ | ExtractedEvent ⚠️
Committed:     is_future_event ✓  | classify_event ✓  | ExtractedCompetition ✓
Impact:        Half done. Still filters past events. Data loss continues.
```

**Parsers:** addington, arena_uk, ashwood, horsevents, my_riding_life, pony_club, showground, british_showjumping, equipe_online

**Example Code (addington.py - BEFORE complete refactor):**
```python
# ❌ Still imports is_future_event
from app.parsers.utils import detect_pony_classes, is_future_event

# ❌ Still filters past events
if not is_future_event(date_start, date_end):
    return None

# ✓ classify_event removed (Phase 4B done)
discipline = None  # EventClassifier will determine

# ❌ API still requests only future events
params = {
    "per_page": PER_PAGE,
    "start_date": today,  # TWO-LAYER FILTERING
}
```

**What's needed:**
```python
# Remove 3 lines:
# 1. is_future_event import
# 2. is_future_event() check
# 3. "start_date": today from API params
```

---

### Pattern 3: False Claims - Completely Untouched ❌ (5 parsers)

Explicitly claimed in Phase 4A as fixed, but git diff is empty. Zero changes applied.

```
Working Tree:  is_future_event ✓  | classify_event ✓  | ExtractedEvent ⚠️
Committed:     is_future_event ✓  | classify_event ✓  | ExtractedCompetition ✓
Impact:        Claimed done but never started. Filters still active.
```

**Parsers:** brook_farm, dean_valley, hartpury, northallerton, port_royal

**Example Code (hartpury.py - UNCHANGED):**
```python
# Line 12: Still imports is_future_event (Phase 4A claim is FALSE)
from app.parsers.utils import detect_pony_classes, infer_discipline, is_future_event

# Line 130: Still filters past events
if not is_future_event(date_start):
    return None

# No changes in working tree (git diff is empty)
```

**Root cause:** These parsers were included in the Phase 4A list because they were *known* to have `is_future_event()`, but the refactoring work was never actually applied to them.

---

### Pattern 4: Completely Untouched, Not in Plan ❌ (5 parsers)

Not included in either phase, yet need both. Completely missed in refactoring scope.

```
Working Tree:  is_future_event ✓  | classify_event ✓  | ExtractedEvent ⚠️
Committed:     is_future_event ✓  | classify_event ✓  | ExtractedCompetition ✓
Impact:        Entire refactoring scope skipped. Multiple filtering layers.
```

**Parsers:** british_showjumping, equipe_online, solihull, sykehouse, horse_events (with extra complications)

**Example Code (solihull.py - UNCHANGED):**
```python
# Line 12: Imports is_future_event
from app.parsers.utils import detect_pony_classes, infer_discipline, is_future_event

# Line 111: Filters past events
if not is_future_event(date_start):
    return None

# No phase 4A or 4B applied
```

**Example Code (horse_events.py - SPECIAL CASE, MOST COMPLEX):**
```python
# Line 14: Still imports classify_event
from app.parsers.utils import classify_event, extract_venue_from_name

# Line 232: Uses classify_event in rallies parsing
discipline, _ = classify_event(name)

# Line 347: Uses classify_event again in detail parsing
discipline, _ = classify_event(name)

# Lines 205-206: Filters in rallies listing
if start_date < today:
    return None

# Lines 321-323: Filters in detail page
if start_dt < today:
    return None

# Lines 268-273: Helper function for URL-based date filtering
def _is_future_url(self, url: str, today: date) -> bool:
    d = _date_from_slug(url)
    if d is None:
        return True
    return d >= today  # THREE FILTERING LAYERS
```

---

## Refactoring Completion Heatmap

```
Status Legend:
  ✓ Complete
  ⚠️ Partial
  ❌ Not done
  ?  Not in scope
```

### By Phase and Parser Count

```
┌─────────────────────────────────────────┐
│ Phase 4A: Remove is_future_event()      │
├─────────────────────────────────────────┤
│ Complete:        23 parsers  [████████] │
│ Partial:          9 parsers  [███]      │
│ False Claims:     5 parsers  [██]       │
│ Untouched:        7 parsers  [██]       │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ Phase 4B: Remove classify_event()       │
├─────────────────────────────────────────┤
│ Complete:        11 parsers  [████]     │
│ Partial:          0 parsers  []         │
│ Untouched:       33 parsers  [███████]  │
│ (33 never had it or were N/A)           │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ Phase 2: Schema rename ExtractedEvent   │
├─────────────────────────────────────────┤
│ Complete:         1 parser   [.]        │
│ Partial:          0 parsers  []         │
│ Untouched:       39 parsers  [█████████]│
└─────────────────────────────────────────┘
```

### Parser State Distribution

```
44 Total Parsers
│
├─ 23 Completely Refactored (52%)
│  └─ Ready to commit
│  └─ Example: british_eventing.py
│
├─ 9 Partially Refactored (20%)
│  └─ Phase 4B done, Phase 4A pending
│  └─ Still filter past events
│  └─ Example: addington.py
│
├─ 5 Claimed but Untouched (11%)
│  └─ False positives (git diff empty)
│  └─ Phase 4A claim not verified
│  └─ Example: hartpury.py
│
├─ 5 Not in Plan (11%)
│  └─ Completely missed by refactoring
│  └─ Include most complex (horse_events)
│  └─ Example: horse_events.py
│
└─ 2 Other (5%)
   └─ Similar to "not in plan"
```

---

## Refactoring Scope Issues

### Issue 1: Phase 4A Claims Don't Match Implementation

**Claimed (REFACTORING_COMPLETE.md):**
```
Phase 4A: Removed date filtering (is_future_event) from 22 parsers
- ballavartyn, british_dressage, british_eventing, brook_farm, bsha, bsps,
  dean_valley, derby_college, epworth, equilive, equo_events, hartpury,
  hickstead, horse_monkey, its_plain_sailing, kelsall_hill, morris,
  northallerton, nsea, nvec, outdoor_shows, port_royal
```

**Actual (Working Tree):**
```
23 parsers refactored (1 more than claimed)
+ 5 parsers claimed but not actually touched (false positives)
+ 5 parsers NOT in the list but also have is_future_event (missed)

Math: 23 (done) - 5 (false claims) + 5 (missed) = 23 that needed it, 17 that got it
Completion rate: 17/23 = 74% (not 22/22 = 100% as claimed)
```

---

### Issue 2: Phase 4B Claims Include Non-Existent Cases

**Claimed (REFACTORING_COMPLETE.md):**
```
Phase 4B: Removed classify_event() calls from 16 parsers:
- abbey_farm, addington, arena_uk, ashwood, asao, entry_master,
  equo_events, hpa_polo, horsevents, kelsall_hill, morris, my_riding_life,
  pony_club, showground, british_horseball, endurance_gb
```

**Actual (Committed Code):**
```
Only 12 parsers HAD classify_event() to remove:
- abbey_farm ✓, addington ✓, arena_uk ✓, ashwood ✓,
  equo_events ✓, horsevents ✓, kelsall_hill ✓, morris ✓,
  my_riding_life ✓, pony_club ✓, showground ✓, horse_events ✓ (not in list!)

4 parsers NEVER had classify_event():
- asao ✗, entry_master ✗, hpa_polo ✗, british_horseball ✗, endurance_gb ✗

2 missing from list:
- horse_events (still has classify_event, not mentioned)
- british_showjumping (should be in Phase 4A but isn't)
```

**Root cause:** The documentation lists parsers to be refactored without verifying they actually have the code that needs refactoring.

---

## What Needs to Happen Next

### Immediate Triage (1 hour)

1. Review the 23 "completely refactored" parsers for quality
2. Identify which changes are safe to commit
3. Plan selective cherry-picking or full revert

### Short-term Fixes (1-2 days)

```
Priority 1: Fix the 9 partially-refactored parsers
  ├─ addington.py      → Remove is_future_event + API param
  ├─ arena_uk.py       → Remove is_future_event
  ├─ ashwood.py        → Remove is_future_event (2 locations)
  ├─ horsevents.py     → Remove is_future_event
  ├─ my_riding_life.py → Remove is_future_event
  ├─ pony_club.py      → Remove is_future_event
  ├─ showground.py     → Remove is_future_event
  ├─ british_showjumping.py → Remove is_future_event
  └─ equipe_online.py  → Remove is_future_event

Priority 2: Fix the 5 "claimed but untouched" parsers
  ├─ brook_farm.py     → Remove is_future_event (1 location)
  ├─ dean_valley.py    → Remove is_future_event (1 location)
  ├─ hartpury.py       → Remove is_future_event (1 location)
  ├─ northallerton.py  → Remove is_future_event (1 location)
  └─ port_royal.py     → Remove is_future_event (1 location)

Priority 3: Fix the 5 completely-untouched parsers
  ├─ solihull.py       → Remove is_future_event (1 location)
  ├─ sykehouse.py      → Remove is_future_event (1 location)
  ├─ horse_events.py   → Remove classify_event (2 locations) + is_future_event (2+ locations)
  ├─ british_showjumping.py → Should be with Priority 1
  └─ equipe_online.py  → Should be with Priority 1

Priority 4: Propagate schema rename
  └─ Update 39 parsers to use ExtractedEvent (or remove backward-compat alias)
```

### Testing (1 day)

```
For each refactored parser:
  [ ] Extract historical events (from 2023-2024)
  [ ] Verify EventClassifier is called (add logging)
  [ ] Verify no date filtering errors
  [ ] Run in Docker, rescan, verify data increase
```

---

## Code Patterns for Quick Reference

### Pattern to Remove (is_future_event)

```python
# ❌ BEFORE
from app.parsers.utils import is_future_event

def _parse_event(self, event):
    date_start = event.get("date")
    if not is_future_event(date_start):
        return None  # Remove this entire block

    # ... rest of parsing
```

```python
# ✓ AFTER
# Remove is_future_event import entirely

def _parse_event(self, event):
    date_start = event.get("date")
    # No date check. All events extracted.

    # ... rest of parsing
```

### Pattern to Remove (classify_event)

```python
# ❌ BEFORE
from app.parsers.utils import classify_event

def _parse_event(self, event):
    name = event.get("title")
    discipline, _ = classify_event(name)
    if not discipline:
        discipline = some_fallback
    # ...
```

```python
# ✓ AFTER
# Remove classify_event import entirely

def _parse_event(self, event):
    name = event.get("title")
    # Don't classify. Let EventClassifier decide.
    discipline = None  # or some_fallback if parser provides hint
    # ...
```

### Pattern to Propagate (Schema Rename)

```python
# ❌ BEFORE (40 parsers)
from app.schemas import ExtractedCompetition
# ... returns list[ExtractedCompetition]

# ✓ AFTER (updated)
from app.schemas import ExtractedEvent
# ... returns list[ExtractedEvent]
```

---

## Conclusion

The refactoring reveals **six distinct patterns** across 44 parsers:

1. **23 completely refactored** - Ready to commit (52%)
2. **9 partially refactored** - Phase 4B done, Phase 4A pending (20%)
3. **5 claimed but untouched** - False positives (11%)
4. **5 completely untouched** - Not in plan (11%)
5. **1 special case** - horse_events.py (most complex, most filtering)
6. **Schema migration** - Incomplete (1/40 parsers)

**Key insight:** The work quality varies greatly. Some parsers are perfectly refactored. Others are false claims. This suggests the refactoring was done locally without systematic verification or commit messages to track progress.
