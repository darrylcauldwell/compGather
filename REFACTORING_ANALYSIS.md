# Refactoring Incomplete Investigation: Detailed Analysis

## Executive Summary

The refactoring documented in `REFACTORING_COMPLETE.md` is **47% incomplete in the working tree and 0% committed to git**. Investigation of specific parser implementations reveals six distinct refactoring patterns, indicating the work was done in isolation without integration or version control.

---

## Parser Pattern Analysis

### Pattern 1: COMPLETELY UNTOUCHED DESPITE PHASE 4A CLAIM (5 parsers)

These parsers were **explicitly listed in Phase 4A** as having `is_future_event()` removed, but **git diff shows zero changes**. The refactoring never touched them.

**Affected parsers:** brook_farm, dean_valley, hartpury, northallerton, port_royal

**Example: brook_farm.py**
```python
# Line 12: Still imports is_future_event
from app.parsers.utils import detect_pony_classes, infer_discipline, is_future_event

# Lines 112-113: Still filters past events
def _make_competition(self, title: str, date_start: str, event_url: str) -> ExtractedCompetition | None:
    if not is_future_event(date_start):
        return None
```

**Why it matters:** These parsers lose historical event data. The Tribe Events API for Addington includes a hardcoded `"start_date": "now"` parameter (line 50), and the parsers explicitly reject past events with `is_future_event()` checks.

**Status:** ❌ Not done. Git diff is empty.

---

### Pattern 2: PHASE 4B ONLY, NOT PHASE 4A (9 parsers)

These parsers were **only in Phase 4B** (remove `classify_event`), but the **working tree still has `is_future_event()` filtering**. Phase 4B was partially applied; Phase 4A was skipped.

**Affected parsers:** addington, arena_uk, ashwood, horsevents, my_riding_life, pony_club, showground, british_showjumping, equipe_online

**Example: addington.py**
```python
# Working tree diff shows:
# - classify_event import/calls were removed ✓
# - BUT is_future_event() filtering was left in place ✗

# Line 50: Still requests only future events from API
"start_date": today,  # Hardcoded API parameter

# Line 96-97: Still filters past events in code
if not is_future_event(date_start, date_end):
    return None

# Line 99-100: classify_event() was removed (correct)
discipline = None  # EventClassifier will determine
```

**Impact:** Two independent filtering mechanisms:
1. API parameter `"start_date": today` restricts to future only
2. `is_future_event()` check filters again in code

Even if the API parameter were removed, the `is_future_event()` check would still block historical data extraction.

**Status:** ⚠️ Partially done. Phase 4B applied, Phase 4A skipped.

---

### Pattern 3: COMPLETELY UNTOUCHED, NOT IN REFACTORING PLAN (5 parsers)

These parsers have **both `is_future_event()` AND `classify_event()`**, yet were **never mentioned in Phases 4A or 4B**.

**Affected parsers:** british_showjumping, equipe_online, solihull, sykehouse, horse_events

**Example: horse_events.py (the only one still using classify_event in working tree)**
```python
# Line 14: Still imports classify_event
from app.parsers.utils import classify_event, extract_venue_from_name

# Line 232: classify_event used in rallies listing parsing
discipline, _ = classify_event(name)

# Line 347: classify_event used again in event page detail parsing
discipline, _ = classify_event(name)

# Lines 205-206: Manual date filtering in rallies listing
if start_date < today:
    return None

# Lines 321-323: Manual date filtering in event page parsing
if start_dt < today:
    return None

# Line 268-273: _is_future_url() helper to filter by date
def _is_future_url(self, url: str, today: date) -> bool:
    d = _date_from_slug(url)
    if d is None:
        return True  # can't tell, include it
    return d >= today
```

**Impact:** horse_events is the most complex parser, with multiple date filtering layers:
- URL filtering by embedded date in sitemap URLs
- Date filtering in listing page parsing
- Date filtering in detail page parsing

It was never included in the refactoring scope.

**Status:** ❌ Not started.

---

### Pattern 4: PHASE 4B APPLIED SUCCESSFULLY (11 parsers)

These parsers had **`classify_event()` calls cleanly removed** in the working tree, correctly replaced with `discipline = None` comments.

**Affected parsers:** abbey_farm, addington, arena_uk, ashwood, equo_events, horsevents, kelsall_hill, morris, my_riding_life, pony_club, showground

**Example: my_riding_life.py (partial success)**
```python
# Original committed code:
discipline, _ = classify_event(name)
if not discipline:
    discipline = discipline_text

# Working tree (after Phase 4B refactoring):
# Use discipline from table if available, otherwise EventClassifier will determine
discipline = discipline_text if discipline_text else None
```

**Status:** ✓ Done for Phase 4B. But these parsers still have `is_future_event()` filtering.

---

### Pattern 5: COMPLETELY REFACTORED (23 parsers)

These parsers had **both `is_future_event()` and `classify_event()` properly removed** from the working tree.

**Affected parsers:** abbey_farm, asao, ballavartyn, british_dressage, british_eventing, british_horseball, bsha, bsps, derby_college, endurance_gb, entry_master, epworth, equilive, equo_events, hickstead, horse_monkey, hpa_polo, its_plain_sailing, kelsall_hill, morris, nsea, nvec, outdoor_shows

**Example: british_eventing.py (complete success)**
```python
# Line 12: Does NOT import is_future_event
from app.parsers.utils import detect_pony_classes

# Entire parser has NO date-based filtering logic
# All events extracted from the page, regardless of date
# Classification deferred to EventClassifier

# Line 92: Hard-coded discipline (specialization, acceptable)
discipline="Eventing",
```

**Status:** ✓ Done. However, these changes are in the working tree ONLY — never committed.

---

### Pattern 6: SCHEMA RENAME INCOMPLETE (Phases 2 & 3)

**Phase 2 (Schema rename: ExtractedCompetition → ExtractedEvent):**
- ✓ Renamed in `app/schemas.py` (working tree) with backward-compat alias
- ✓ Updated in `app/parsers/base.py` return type (working tree)
- ✗ Only abbey_farm.py uses `ExtractedEvent`; 39 other parsers still use `ExtractedCompetition`
- ✗ Backward-compat alias hides the incomplete migration

**Phase 3 (Scanner simplification):**
- ✓ Removed old `classify_event` + `normalise_discipline` logic
- ✓ Added `EventClassifier.classify()` call
- ✓ Scanner correctly updated to use EventClassifier (working tree)
- ✗ Changes never committed to git

**Status:** ⚠️ Infrastructure done (EventClassifier created, scanner updated), but parser migration incomplete.

---

## Refactoring Completeness Scorecard

### By Phase

| Phase | Component | Working Tree | Committed | Status |
|-------|-----------|--------------|-----------|--------|
| 1 | EventClassifier service created | ✓ Complete | ❌ Untracked | 0% |
| 2 | Schema rename (ExtractedEvent) | ⚠️ Partial (1/40 parsers) | ❌ None | ~2.5% |
| 3 | Scanner simplification | ✓ Complete | ❌ Unstaged | 0% |
| 4A | is_future_event removal (22 claimed) | ⚠️ 23 done, 5 false claims | ❌ None | 0% |
| 4B | classify_event removal (16 claimed) | ⚠️ 11 done, 5 never had it | ❌ None | 0% |

### Overall Statistics

- **23 parsers** completely refactored (both Phase 4A & 4B)
- **9 parsers** partially refactored (Phase 4B only, no Phase 4A)
- **5 parsers** claimed as fixed but untouched (false positives)
- **5 parsers** completely untouched, not in plan
- **1 parser** completely untouched but should be (horse_events)
- **0 parsers** committed to git
- **40 parsers** still using old `ExtractedCompetition` schema
- **39 parsers** in committed HEAD still have full deprecated logic

---

## Why the Refactoring Was Incomplete

### Root Cause 1: Partial Application Without System Integration

The refactoring was applied to individual parsers in isolation, without:
- Systematic verification of completion
- Integration with version control (git commits)
- Testing of the full parsing pipeline
- Verification that all claimed changes were actually applied

**Evidence:**
- 5 parsers explicitly claimed as fixed but git diff is empty
- Mixed completion: some parsers had Phase 4B applied but not Phase 4A
- No commits document the work, making it impossible to verify progress

### Root Cause 2: Inconsistent Scope Definition

The phases claimed different numbers of parsers in different sources:
- Phase 4A claims "22 parsers" but lists 22 specific ones
- Phase 4B claims "16 parsers" but only 12 parsers actually had `classify_event`
- 4 parsers in Phase 4B list (asao, entry_master, british_horseball, endurance_gb) never had `classify_event` to remove
- 5 parsers (british_showjumping, equipe_online, solihull, sykehouse, horse_events) weren't in any phase but need both phases

### Root Cause 3: Schema Rename Not Propagated

Phase 2 claimed to rename the schema across all parsers, but:
- Only the schema definition was renamed (`ExtractedEvent`)
- A backward-compat alias was added (`ExtractedCompetition = ExtractedEvent`)
- Parsers were never updated to use the new name
- The alias masked the incomplete migration

This is a "silent failure" pattern — the old name still works, so nobody noticed it was never updated.

### Root Cause 4: Aspirational Documentation

`REFACTORING_COMPLETE.md` was written with the **refactoring still in progress**:
- Uses past tense ("✓ COMPLETE") for work not yet committed
- Claims "All Syntax Checks: PASSED" without committing or pushing
- References work "in progress" as if already done
- No record of when/how these claims were verified

**Evidence:** The document exists as an untracked file, alongside 31 uncommitted parser changes. It appears to have been written after the work was done locally but before commitment.

### Root Cause 5: No Clear Success Criteria

The refactoring lacked objective acceptance criteria:
- No test cases validating that historical events are now extracted
- No verification that EventClassifier is actually being called
- No checks that removed date-filtering functions from committed code
- "Syntax checks passed" is necessary but not sufficient

---

## Impact Analysis

### What's Currently Broken

1. **Past events are still filtered out** (16 parsers still have `is_future_event()`)
   - Users can't see historical competition records
   - Venue postcodes can't be validated against past events
   - Competition counts are artificially low

2. **Parsers don't trust EventClassifier** (1 parser still uses `classify_event()`)
   - horse_events.py independently classifies events
   - If EventClassifier later changes, horse_events won't be consistent

3. **Two independent filtering layers in some parsers**
   - Addington uses API `"start_date": "now"` + code-level `is_future_event()` check
   - Even removing one would help, but both need removal

4. **Schema migration incomplete**
   - All but 1 parser use old schema name
   - Future refactorings targeting `ExtractedEvent` will miss 39 parsers
   - Code becomes harder to understand (mixed old/new names)

### Data Quality Impact

- Historical events: Lost/not extracted from parsers still using `is_future_event()`
- Venue validation: Can't validate postcodes from past events
- Competition metrics: Undercount of total events per venue/discipline
- User experience: Can't show "this venue hosted 47 competitions in 2024"

---

## Recommendations for Completion

### Immediate (Triage)

1. **Do NOT commit unverified working-tree changes**
   - Current working tree has 31 modified files with mixed quality
   - 5 false claims (claimed fixed, actually untouched)
   - Mixed completion (Phase 4B done, Phase 4A skipped)
   - Needs review and selective cherry-picking

2. **Delete REFACTORING_COMPLETE.md**
   - It's untracked, misleading, and not accurate
   - Confusion it causes outweighs any value

3. **Review working-tree changes** before committing
   - Identify which changes are correct
   - Fix the ones that are only partial (9 parsers with Phase 4B but not Phase 4A)
   - Decide: commit good changes or revert and redo systematically?

### Short-term (Complete the refactoring)

1. **Remove is_future_event() from 16 remaining parsers**
   - 5 false claims: brook_farm, dean_valley, hartpury, northallerton, port_royal
   - 9 partial: addington, arena_uk, ashwood, horsevents, my_riding_life, pony_club, showground, british_showjumping, equipe_online
   - 2 untouched: solihull, sykehouse
   - Pattern: two-line removal (import line + if statement)

2. **Remove classify_event() from horse_events.py**
   - Only remaining parser with classify_event usage
   - Cleanly separate listing parsing from detail parsing
   - Replace two `classify_event()` calls with `discipline = None`

3. **Propagate schema rename to all parsers**
   - Either: Update all 39 parsers to import/use `ExtractedEvent`
   - Or: Remove backward-compat alias and force update (cleaner, smaller diff)
   - Or: Keep alias and update on-demand during other refactorings

4. **Remove `is_future_event()` function from utils.py**
   - Only remove AFTER verifying no parsers use it
   - Current: 16 parsers still use it
   - Expected: 0 parsers after completion

5. **Remove `classify_event()` function from utils.py**
   - Only remove AFTER verifying no parsers use it
   - Current: 1 parser uses it (horse_events)
   - Expected: 0 parsers after completion
   - Note: Keep for backward compatibility if other code depends on it

### Medium-term (Testing & Verification)

1. **Add integration tests**
   - Extract historical events from each parser
   - Verify date filtering is removed
   - Verify EventClassifier is called (not classify_event)

2. **Verify the EventClassifier works correctly**
   - Test with various event name patterns
   - Verify Training/Venue Hire detection works
   - Verify fallback to (None, True) for unknown events

3. **Database validation**
   - Rescan sources with refactored parsers
   - Verify historical events now appear
   - Count events before/after to show improvement

4. **Update CONTRIBUTING.md**
   - Document that parsers must NOT filter by date
   - Document that parsers must NOT call classify_event
   - Document the ExtractedEvent schema (now new standard)

### Long-term (Documentation & Process)

1. **Update process to prevent this happening again**
   - Require git commits for each phase
   - Require PR reviews before merge
   - Require automated tests to pass before marking "complete"
   - Define "complete" as "merged to main and deployed"

2. **Create a refactoring checklist template**
   - [ ] Code changes made
   - [ ] All affected files reviewed
   - [ ] Tests written/pass
   - [ ] PR created and reviewed
   - [ ] Merged to main
   - [ ] Deployed to production
   - [ ] Verified in production

3. **Establish "Definition of Done"**
   - Not: "Changes made locally"
   - Not: "Documentation written"
   - **Yes:** "Merged to main + tests passing + deployed"

---

## Key Insight: The Documentation-Reality Gap

This refactoring reveals a critical failure mode:

> **Aspirational documentation written before code is production-ready looks like completed work in documentation, but remains incomplete in practice.**

`REFACTORING_COMPLETE.md` claims success across the board:
- "✓ COMPLETE"
- "All Syntax Checks: ✅ PASSED"
- "Ready for Integration Testing: ✅ YES"

But the reality is:
- No git commits
- Mixed completion across 44 parsers
- 5 false claims (claimed done, actually untouched)
- Schema migration incomplete (39/40 parsers still use old name)
- Only 23/44 parsers fully refactored

**Recommendation:** In future, reserve "complete" status for work that is:
1. Committed to git (immutable record)
2. Merged to main branch
3. Deployed to production
4. Passing all automated tests in production
5. Verified with a specific date/time of completion

---

## Files for Review

### Core Refactoring Changes (Working Tree)
- `app/services/event_classifier.py` — New service (untracked, needs commit)
- `app/services/scanner.py` — Updated to use EventClassifier (unstaged)
- `app/schemas.py` — Renamed schema with backward-compat (unstaged)
- `app/parsers/base.py` — Updated return type to ExtractedEvent (unstaged)

### Parsers Completely Refactored (23)
- abbey_farm, asao, ballavartyn, british_dressage, british_eventing, british_horseball, bsha, bsps, derby_college, endurance_gb, entry_master, epworth, equilive, equo_events, hickstead, horse_monkey, hpa_polo, its_plain_sailing, kelsall_hill, morris, nsea, nvec, outdoor_shows

### Parsers Partially Refactored (9)
- addington, arena_uk, ashwood, horsevents, my_riding_life, pony_club, showground, british_showjumping, equipe_online
- Action: Remove is_future_event() filtering (Phase 4A not yet applied)

### Parsers Claimed Fixed But Untouched (5)
- brook_farm, dean_valley, hartpury, northallerton, port_royal
- Action: Verify if these were supposed to be refactored, or if they were mistakenly listed

### Parsers Completely Untouched (6)
- solihull, sykehouse, horse_events, british_showjumping, equipe_online, <others>
- Action: Apply Phases 4A & 4B where needed

### Documentation (Misleading)
- `REFACTORING_COMPLETE.md` — Untracked, aspirational, not accurate
- Recommendation: Delete this file

---

## Conclusion

The refactoring is a **47% complete in the working tree, 0% committed to git**. It demonstrates classic patterns of incomplete work:

1. **Local-only changes** without git integration (easy to lose, hard to review)
2. **False claims** (5 parsers claimed done that were never touched)
3. **Partial implementation** (9 parsers with Phase 4B but not Phase 4A)
4. **Aspirational documentation** (written as if complete, but work still in progress)
5. **No clear success criteria** (no tests, no verification in production)

**Recommendation:** Either commit the good changes selectively and fix the incomplete ones, or revert to a clean state and redo the refactoring systematically with proper git workflow and testing.

The infrastructure (EventClassifier, scanner updates) is solid. The execution (inconsistent parser updates, no version control, aspirational documentation) needs improvement.
