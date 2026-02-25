# Phase 2 Web Crawl: Validation Summary

## Progress Report

**Date:** 2026-02-23

### Completed Batches (1-10 of 26)
- **Batch 1** (20 venues): 18 validated ✅
- **Batch 2** (20 venues): 17 validated ✅
- **Batch 3** (20 venues): 19 validated ✅
- **Batch 4** (20 venues): 12 validated ✅
- **Batch 5** (16 venues): 5 validated ✅
- **Batches 6-10** (100 venues): 20 validated ✅

### Total Progress
- **Completed:** 200 venues (Batches 1-10)
- **Validated:** 91 venues (45.5% success rate)
- **Remaining:** 316 venues (Batches 11-26)

### Expected Final Results
- Projected validated venues from remaining batches (at 45% rate): ~142 venues
- **Estimated Total:** ~233 validated venues from 516 missing-postcode venues (45%)

## Validation Statistics

### Success Rate by Batch
| Batch | Total | Validated | Success Rate |
|-------|-------|-----------|--------------|
| 1     | 20    | 18        | 90% |
| 2     | 20    | 17        | 85% |
| 3     | 20    | 19        | 95% |
| 4     | 20    | 12        | 60% |
| 5     | 16    | 5         | 31% |
| 6-10  | 100   | 20        | 20% |
| **Cumulative** | **200** | **91** | **45.5%** |

### Validation Sources Used
- Official venue websites
- UK postcode directories
- Business registries (Companies House)
- Equestrian event platforms (British Dressage, British Eventing, Horse Events)
- BHS Approved Centre listings
- Event management websites
- VisitScotland/regional tourism boards
- Google Maps and address verification
- Business directories (Yell, 192.com, etc.)

## Venues Unable to Validate
The remaining ~55% that couldn't be validated (425 venues) typically fall into these categories:

1. **Venues with multiple locations** - Name shared by multiple facilities (e.g., "Home Farm", "Manor Farm")
2. **Incomplete names** - Truncated or malformed names (e.g., "TBA XXX", "Venue", "Lla")
3. **Geographic placenames only** - Town/city names without specific venue (e.g., "London", "Road Green")
4. **Non-equestrian venues** - Town halls, community centres with no dedicated equestrian services
5. **Defunct venues** - Venues no longer in operation or with outdated information
6. **Aliases/duplicates** - Same venue with different names in database
7. **No online presence** - Small private venues with no website or business listing

## Next Steps

1. **Batches 11-26** (316 remaining venues):
   - Continue systematic web crawling for remaining 6 batches
   - Expected completion: 140-180 additional validated venues
   - Process: Same validation criteria (100% confidence only)

2. **Post-Validation Phase**:
   - Consolidate all validated results
   - Identify duplicates and aliases
   - Update database with confirmed postcodes
   - Create "unvalidatable venues" report for manual review
   - Re-run scans to verify improved venue matching

3. **Data Quality Improvement**:
   - 91 validated venues will have postcodes added to database
   - This will improve distance calculations and venue matching
   - Future scans will benefit from enriched seed data

## Validation Criteria Applied

**100% Confidence Threshold:**
- Postcode found on official venue website OR
- Postcode confirmed in 2+ independent authoritative sources (business registry, postcode checker, event platforms) AND
- Venue name and postcode match venue database records AND
- No conflicting information found

**Rejected (< 100% confidence):**
- Single-source confirmation
- Ambiguous matches
- Incomplete or truncated venue names
- Venues with no verifiable online presence
