# Deprecated Parser Logic Analysis

## Summary

There are **extensive traces of deprecated event filtering and classification logic** throughout the codebase. The architecture has evolved to move filtering and classification out of parsers and into a secondary classifier process, but this migration is incomplete.

**Status**: 34 out of 43 parsers still contain deprecated filtering logic that should be removed.

---

## Core Issue: Misunderstanding of Responsibility

### Current (Deprecated) Pattern
```
Parser → [filters events] → [classifies events] → ExtractedCompetition
                                                   ↓
                                         Scanner → Database
```

### Intended (New) Pattern
```
Parser → [extracts ALL raw data] → ExtractedCompetition
                                   ↓
                        Scanner + Classifier → Database
```

The comments in the codebase confirm this (see `app/parsers/utils.py:252-254`):
```python
def should_skip_event(discipline: str | None, name: str) -> bool:
    """Return True if an event would be classified as non-competition.

    Deprecated: parsers should no longer skip events.  Instead, capture
    all events and let classify_event() / the scanner determine
    is_competition.  Kept for backward compatibility during migration.
    """
```

---

## Problem 1: Date Filtering in Parsers (CRITICAL)

### Pattern: `if not is_future_event(date_start, date_end): continue`

**Affected Parsers (34 total)**:
- abbey_farm, addington, arena_uk, asao, ashwood, ballavartyn
- british_dressage, british_eventing, brook_farm, bsha, bsps
- dean_valley, derby_college, entry_master, epworth, equilive
- equo_events, hartpury, hickstead, horse_monkey, horsevents
- its_plain_sailing, kelsall_hill, morris, my_riding_life
- northallerton, nsea, nvec, outdoor_shows, pony_club
- port_royal, showground, solihull, sykehouse

### Issue
Parsers are using `is_future_event()` to **skip past events entirely**. This:
1. **Breaks the Abbey Farm event** — A training clinic dated 2026-02-25 (today or future) passes the filter, but contains "Training" in the name, which triggers non-competition classification in the scanner
2. **Breaks historical/past event support** — Any parser run that encounters past events will lose them
3. **Violates single-responsibility principle** — Parsers should extract, not filter
4. **Makes testing difficult** — Can't test past-date scenarios in unit tests without mocking dates

### Example: `my_riding_life.py:118-119`
```python
if not is_future_event(date_start, date_end):
    continue  # DEPRECATED: Skip past events
```

### Example: `abbey_farm.py:89-90`
```python
if not is_future_event(date_start, date_end):
    return None  # DEPRECATED: Skip past events
```

---

## Problem 2: Event Classification (is_competition) Logic

### Pattern A: Ignoring `classify_event()` Return Value

**13 parsers call `classify_event()` but discard the `is_competition` flag:**

```python
discipline, _ = classify_event(name)  # ❌ Throws away is_competition!
```

Affected parsers:
- abbey_farm, asao, british_horseball, endurance_gb, entry_master
- hpa_polo, horsevents, my_riding_life, pony_club, showground

### Issue
The `classify_event()` function is explicitly designed to return:
```python
def classify_event(name: str, description: str = "") -> tuple[str | None, bool]:
    """Returns (discipline, is_competition)

    For training events: ("Training", False)
    For venue hire:      ("Venue Hire", False)
    For competitions:    (<discipline>, True)
    """
```

But parsers throw away the second value, leaving it to the scanner to re-determine. This:
1. Creates duplicate logic — both parsers AND scanner call `classify_event()`
2. Misses the parser's domain knowledge — the parser could be smarter about whether something is a competition
3. Violates DRY principle

### Example: `abbey_farm.py:98`
```python
discipline, _ = classify_event(name)  # ❌ Ignores is_competition
```

### Example: `my_riding_life.py:144`
```python
discipline, _ = classify_event(name)  # ❌ Ignores is_competition
```

---

## Problem 3: Scanner Has Become a Secondary Classifier

### Current Scanner Logic (`app/services/scanner.py:267-285`)

The scanner is now doing the classification that should have been done in parsers:

```python
# Line 267-268: Normalise parser-provided discipline
discipline, is_competition = normalise_discipline(comp_data.discipline)

# Line 272-279: OVERRIDE with event name classification
name_discipline, name_is_comp = classify_event(comp_data.name)
if not name_is_comp:
    # Name contains non-competition keywords — override to non-competition
    is_competition = False
    if not discipline or discipline == comp_data.discipline:
        discipline = name_discipline

# Line 282-285: Track the classification result
if is_competition:
    scan_comp_count += 1
else:
    scan_training_count += 1
```

**This is a workaround**, not the intended design. The scanner:
1. Calls `normalise_discipline()` to get `is_competition`
2. Then calls `classify_event()` to potentially override it
3. Tracks competition vs training counts as a side effect

---

## Problem 4: ExtractedCompetition Schema Missing is_competition Field

### Issue in `app/schemas.py:76-89`

```python
class ExtractedCompetition(BaseModel):
    name: str
    date_start: str
    date_end: str | None = None
    venue_name: str
    venue_postcode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    discipline: str | None = None
    has_pony_classes: bool = False
    classes: list[str] = []
    url: str | None = None
    description: str | None = None
    # ❌ NO is_competition FIELD!
```

Because `ExtractedCompetition` lacks an `is_competition` field:
1. Parsers can't communicate whether they think something is a competition
2. The scanner always defaults events to `is_competition=True` (from Competition model default)
3. This means the Abbey Farm "Training Clinic" is stored as `is_competition=True` despite being training

---

## Specific Case Study: Abbey Farm Event

The missing Abbey Farm event ("Maddy Moffet Jump Polework Training Clinic") is a direct result of these deprecated patterns:

1. **Parser level** (`abbey_farm.py:98`):
   ```python
   discipline, _ = classify_event(name)  # Gets ("Training", False)
   # But throws away the False! Never communicates it's non-competition
   ```

2. **Scanner level** (`scanner.py:267-279`):
   ```python
   # Scanner re-classifies the event based on name
   name_discipline, name_is_comp = classify_event(comp_data.name)
   if not name_is_comp:
       is_competition = False  # Set to False
   ```

3. **Database**:
   The event IS stored with `is_competition=False` (based on scanner logic)

4. **Page filter** (`routers/pages.py:211-212`):
   ```python
   if not (cleaned_disciplines and all(d in _NON_COMPETITION_DISCIPLINES for d in cleaned_disciplines)):
       stmt = stmt.where(Competition.is_competition == True)
   ```
   Non-competition events are hidden UNLESS the user specifically filters by a non-competition discipline

**Result**: Training/clinic event is stored but hidden from the default view.

---

## Deprecated Functions That Should Be Removed from Parsers

| Function | Purpose | Should Use Instead |
|----------|---------|-------------------|
| `is_future_event(date_start, date_end)` | Filter past events | Remove entirely — extract all events; let classifier decide |
| `classify_event(name, description)` | Determine discipline & is_competition | Use for description only; scanner will re-classify |
| `should_skip_event(discipline, name)` | Determine if event should be included | Remove entirely — defined in utils but never used in parsers |
| `normalise_discipline(raw)` | Normalize discipline string | OK to use for standardizing discipline text |
| `detect_pony_classes(text)` | Detect pony class mentions | OK to use — purely information extraction |
| `extract_postcode(text)` | Extract UK postcodes | OK to use — purely information extraction |

---

## Recommended Fixes

### Immediate (Must-Do)

1. **Remove date filtering from ALL 34 parsers**
   - Delete `if not is_future_event(...)` checks
   - Extract all events regardless of date
   - Rationale: Historical data is valuable; classifier can filter later if needed

2. **Add `is_competition: bool | None = None` to `ExtractedCompetition`**
   - Allows parsers to communicate their classification
   - If parser provides value, scanner should trust it (only override if confident)
   - Rationale: Preserve parser domain knowledge

3. **Update scanner logic to prioritize parser classification**
   - Use `comp_data.is_competition` if provided
   - Only fallback to `classify_event()` if parser didn't provide one
   - Rationale: Single source of truth

### Medium-term (Cleanup)

4. **Create dedicated `EventClassifier` class**
   - Centralize all classification logic
   - Replace the scattered `classify_event()` calls in scanner
   - Handle edge cases uniformly
   - Rationale: Reduce duplicate logic

5. **Add explicit "Training" and "Venue Hire" viewing**
   - Don't hide non-competition events
   - Add filter UI to show/hide by event type
   - Rationale: Users may want to see clinics and training events

6. **Document the expected ExtractedCompetition schema**
   - Each field should be clearly documented
   - Explain what parsers can/should provide
   - Rationale: Reduce confusion in future

---

## Summary Table: Deprecated Patterns by Parser

| Parser | is_future_event | classify_event | Ignores is_comp | Count |
|--------|:---:|:---:|:---:|:---:|
| abbey_farm | ✓ | ✓ | ✓ | 3 |
| addington | ✓ | - | - | 1 |
| arena_uk | ✓ | - | - | 1 |
| asao | ✓ | ✓ | ✓ | 3 |
| ashwood | ✓ | - | - | 1 |
| ballavartyn | ✓ | - | - | 1 |
| british_dressage | ✓ | - | - | 1 |
| british_eventing | ✓ | - | - | 1 |
| british_horseball | - | ✓ | ✓ | 2 |
| brook_farm | ✓ | - | - | 1 |
| bsha | ✓ | - | - | 1 |
| bsps | ✓ | - | - | 1 |
| dean_valley | ✓ | - | - | 1 |
| derby_college | ✓ | - | - | 1 |
| endurance_gb | - | ✓ | ✓ | 2 |
| entry_master | ✓ | ✓ | ✓ | 3 |
| epworth | ✓ | - | - | 1 |
| equilive | ✓ | - | - | 1 |
| equo_events | ✓ | - | - | 1 |
| hartpury | ✓ | - | - | 1 |
| hickstead | ✓ | - | - | 1 |
| horse_events | - | - | - | 0 |
| horse_monkey | ✓ | - | - | 1 |
| horsevents | ✓ | ✓ | ✓ | 3 |
| hpa_polo | - | ✓ | ✓ | 2 |
| its_plain_sailing | ✓ | - | - | 1 |
| kelsall_hill | ✓ | - | - | 1 |
| morris | ✓ | - | - | 1 |
| my_riding_life | ✓ | ✓ | ✓ | 3 |
| northallerton | ✓ | - | - | 1 |
| nsea | ✓ | - | - | 1 |
| nvec | ✓ | - | - | 1 |
| outdoor_shows | ✓ | - | - | 1 |
| pony_club | ✓ | ✓ | ✓ | 3 |
| port_royal | ✓ | - | - | 1 |
| showground | ✓ | ✓ | ✓ | 2 |
| solihull | ✓ | - | - | 1 |
| sykehouse | ✓ | - | - | 1 |
| **TOTAL** | **34** | **13** | **11** | **~50** |

---

## Detailed Examples

### Pattern 1: is_future_event filtering

**abbey_farm.py:89-90**
```python
if not is_future_event(date_start, date_end):
    return None
```

**epworth.py:123**
```python
if not is_future_event(current_date):
    continue
```

**nvec.py:110**
```python
if not is_future_event(date_start):
    continue
```

### Pattern 2: classify_event with ignored is_competition

**abbey_farm.py:98-108**
```python
discipline, _ = classify_event(name)  # Throws away is_competition!

# If classify_event didn't find a discipline, try event categories
categories = event.get("categories", [])
if not discipline and categories:
    for cat in categories:
        cat_name = cat.get("name", "")
        disc, _ = classify_event(cat_name)  # Again, throws away is_competition!
        if disc:
            discipline = disc
            break
```

**my_riding_life.py:144**
```python
discipline, _ = classify_event(name)
if not discipline:
    discipline = discipline_text
```

**asao.py** (similar pattern)
```python
disc, _ = classify_event(event_name)
```

---

## Configuration Context

This deprecated logic is documented in:
- `CLAUDE.md`: "Parsers: extend BaseParser, register with @register_parser("key")"
- `docs/BEST_PRACTICES.md`: Should contain guidance on parser responsibility
- `app/parsers/utils.py:252-254`: Explicit deprecation comment in `should_skip_event()`

The intended design is described in the comments, but the implementation is incomplete.
