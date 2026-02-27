# Venue Alias Report — 25 Feb 2026

**Database snapshot**: 1,206 venues (738 seeded, 468 dynamic), 9,197 competitions

## Summary

| Category | Count |
|----------|-------|
| Postcodes with multiple venues | 43 |
| Clear aliases to add to seed data | 30 |
| Same venue, different suffix/address | 15 |
| Genuinely different venues at same postcode | 5 |
| Venue name normalisation fixes needed | 7 |
| No-postcode venues needing seed aliases | 20 |

---

## Section 1: Clear Aliases (same postcode, dynamic matches seeded venue)

These dynamic venues share a postcode with a seeded venue and are clearly the same place.
**Action**: Add each dynamic name as an alias in `venue_seeds.json`, then run `scripts/renormalise_venues.py`.

| Postcode | Seed Venue (canonical) | Dynamic Name (add as alias) | Events |
|----------|----------------------|---------------------------|--------|
| BB6 8BE | Northcote | Northcote Stud Evening | 1 |
| BT27 5NW | Danescroft Equestrian Centre | Danescroft Equestrian Centre, Lisburn | 1 |
| CA4 8DH | Murray House Livery | Murray House | 1 |
| CV47 2DL | Dallas Burston Polo Club | Dallas Burston Polo Club Stoneythorpe Estate Southam Warwickshire | 1 |
| CW11 4TJ | Darlington Stables, Hooten Hall Lane | Darlington Stables | 1 |
| CW12 4SW | Somerford Park Farm | Somerford Park Holmes Chapel Road, Congleton | 1 |
| DA3 8NJ | Speedgate Farm | Speedgate Enterprises | 1 |
| EH48 4NE | Champfleurie | Champfleurie Stables | 1 |
| GL4 8LJ | Sidelands Farm, Birdlip | Sidelands Farm | 1 |
| GL7 5FD | The Talland School Of Equitation, Dairy Farm | The Talland School | 3 |
| GU52 8AD | Tweseldown | Tweseldown Bourley Road Church Crookham Fleet | 1 |
| KA3 6AY | Morris | Morris Equestrian Meikle Mosside Farm Cottage | 1 |
| LE7 3RX | Barrowcliffe | Barrowcliffe Xc | 7 |
| PL21 0HG | The Brook | The Brook Ugborough Rd Bittaford | 1 |
| SO21 2NF | Sparsholt | Sparsholt Equine College Winchester | 1 |
| SO41 5ZG | Walhampton School, Lymington | Walhampton School | 2 |
| SY22 6LG | Radfords Equestrian Centre | Radfords Lower House Farm, Llanymynech | 1 |
| TA6 4SR | Stretcholt Farm | Stretcholt Lane, Stretcholt | 1 |
| TD14 5LN | Reston | Sunnyside, Reston | 2 |
| TQ10 9HL | Cheston Farm Equestrian Centre | Cheston | 5 |
| YO42 4DD | Thornton House Farm | Thornton House Farm, Livery Yard | 1 |

---

## Section 2: Kelsall Hill / Arena UK / Bicton — Event-name-as-venue-name

These are venue names that include event descriptions. The normaliser should strip these, or they need aliases.

### CW6 0SR — Kelsall Hill (141 events in seed)
| Dynamic Name | Events |
|-------------|--------|
| Kelsall Hill British Dressage | 2 |
| Kelsall Hill British Showjumping Cat 1 | 1 |
| Kelsall Hill British Showjumping Cat 2 | 1 |
| Kelsall Hill British Showjumping Large Pony Premier | 1 |
| Kelsall Hill British Showjumping Small Pony Premier | 1 |
| Kelsall Hill Clear Round Showjumping | 3 |

### NG32 2EF — Arena UK (96 events in seed)
| Dynamic Name | Events |
|-------------|--------|
| Arena Uk (Small Pony Premier) Sat 7Th | 1 |
| Arena Uk 2Nd | 1 |
| Arena Uk Tuesday | 1 |
| Assisted | 1 |
| Large Pony Premier With 2Nd Ring Outside 28Th Feb | 1 |
| Para Winter Championships 19Th | 1 |

### EX9 7BL — Bicton (62 events in seed)
| Dynamic Name | Events |
|-------------|--------|
| Bicton : Unaffiliated Arena Eventing | 1 |
| Bicton Training Show (90Cm-1.30M) | 1 |
| Bicton: British Dressage | 1 |

### No postcode — Onley Grounds (seed: CV23 8AJ)
| Dynamic Name | Events |
|-------------|--------|
| Onley Grounds British Showjumping | 1 |
| Onley Grounds Clear Round | 5 |
| Onley Grounds Junior British Showjumping | 1 |
| Onley Grounds Senior British Showjumping | 4 |
| Onley Grounds Training Show | 1 |
| Onley Grounds Unaffiliated Showjumping | 3 |

**Action**: These likely need normaliser improvements (stripping event-type suffixes from venue names). Alternatively, add as aliases.

---

## Section 3: No-Postcode Venues — Confident Matches

These dynamic venues have no postcode but clearly match a seeded venue by name.
**Action**: Add as aliases in `venue_seeds.json`.

| Seed Venue (canonical) | Seed Postcode | Dynamic Name (add as alias) | Events |
|------------------------|--------------|---------------------------|--------|
| Bishop Burton | HU17 8QG | Bishop Burton College, Beverley | 1 |
| Burghley | PE9 3JY | Burghley Horse Trials | 1 |
| Burnham Market International | PE31 8JY | Burnham Market International Sponsored By Barefoot Retreats | 1 |
| Chard | TA20 4BP | Chard Equestrian Ltd (P-Gp/Pyo Fei)+Fs | 1 |
| Chard | TA20 4BP | Chard Equestrian Ltd (P-Gp/Pyo Fei)+Fs+Pe (I-Gp)+Fs+Pe | 2 |
| Chard | TA20 4BP | Chard Equestrian Quest League And Summerleaze Vets | 1 |
| Chard | TA20 4BP | Chard Equestrian Summerleaze Vets | 1 |
| Chiverton | TR4 8JQ | Chiverton Riding Centre Rda | 1 |
| Dyffryn Farm, Dyffryn Lane | SY21 8AE | Dyffryn Farm | 1 |
| Golden Cross | BN27 3SS | Smp@Golden Cross | 3 |
| Hickstead | BN6 9NS | Hickstead, The All England Jumping Course | 1 |
| Kirkley Hall | NE20 0AQ | Kirkley Hall College | 1 |
| Leadenham Polo Club Arena | LN5 0PP | Leadenham Polo Club | 3 |
| Little Gatcombe | GL6 9AT | Little Gatcombe Sponsored By Stroud Farm Services | 1 |
| Mendip Plains | BA3 4BX | Mendip Plains Ston Easton | 1 |
| Moreton Morrell | CV35 9BL | Moreton Morrell Equestrian Centre, Warks | 2 |
| Pickering Grange | LE67 1EZ | Pickering Grange Equestrian Centre, Leics | 2 |
| Solihull Riding Club | B93 8QE | Solihull Riding Club, Solihull | 1 |
| South Of England Showground | RH17 6TL | South Of England | 1 |
| Thoresby Park International Event Centre | NG22 9EP | Thoresby Park International Eventing Spring Carnival | 1 |
| Tichborne Park | SO24 0PN | Tichborne Park - S)24 0Pn | 1 |
| Haie Fleurie | JE3 6BN | La Haie Fleurie Stable | 1 |
| Waverton House | GL56 9TB | Waverton | 1 |
| Wellington Riding | RG27 0LJ | Wellington, Heckfield | 2 |
| Scottish National Equestrian Centre | EH52 6NH | Scottish National | 6 |
| Scottish National Equestrian Centre | EH52 6NH | The Scottish National | 3 |

---

## Section 4: Seed-to-Seed Duplicates

These are seeded venues that share a postcode — may need merging.

| Postcode | Venue 1 | Events | Venue 2 | Events |
|----------|---------|--------|---------|--------|
| AL3 7PT | Herts County Show | 1 | Herts County Showground | 0 |
| PR3 0RY | Myerscough College | 33 | Myerscough College St Michael's Road | 0 |
| TS27 3HP | Dalton Indoor | 1 | Dalton Piercy | 2 |

**Action**: Consider merging — "Herts County Show" is likely an alias of "Herts County Showground". "Myerscough College St Michael's Road" (0 events) can be removed or aliased. Dalton Indoor and Dalton Piercy may be different arenas at the same site.

---

## Section 5: Same Postcode, Different Venues (no action needed)

These share a postcode but appear to be genuinely different places.

| Postcode | Venues |
|----------|--------|
| BH31 6JA | Cranebrook (3), Verwood Manor Farm (2) |
| CB8 9DG | Cheveley Parish Hall (1), High Street (3) |
| CV35 7AX | National Presentation (0), Lowlands Equestrian Centre (1), On Line (1) |
| DL2 2PP | Julia Nelson (1), Willow Lake Lodge (1) |
| GL6 8HZ | Oxstalls (5), Tyning Villa Stables (3) |
| HG5 0SE | Allerton Park (1), Paddock House (2) |
| LE9 7TF | Lakeside (4), The Manor Thurlaston (1) |
| LS25 6JX | Half Term (1), Stressless Sj Xpoles 35Cm (1) |
| OX12 9NJ | Fawley House Stud (2), Fawley House Stud Fawley Oxfordshire (1) |
| OX15 4JA | Oak Tree Farm (1), Oak Tree Farm Xc (3) |
| PE8 6NR | Grange Farm Equestrian Centre (2), Wittering Grange (2) |
| SA10 9HL | Cae John (1), Pony Club Field, Onllwyn (4) |
| TR8 4JL | Porth Valley Equestrian (0), Hendra Paul Livery Yard (1), Porth Valley (4) |
| WR9 0BE | Gracelands (4), Dodderhill (2) |

**Note**: Some of these may actually be aliases — investigate LS25 6JX ("Half Term" looks like an event name not a venue), OX12 9NJ and OX15 4JA look like aliases (with/without address suffix), and TR8 4JL "Porth Valley" is likely alias of "Porth Valley Equestrian".

---

## Section 6: Junk Venue Names (data quality issues)

These dynamic venues without postcodes are clearly not venue names — they're event data leaking into the venue field.

| Venue Name | Events | Issue |
|-----------|--------|-------|
| 00:00:00Area Quizarea Quiz | 1 | Time + event name |
| 00:00:00Rally For All Levels - Connellhill... | 1 | Time + event name |
| 21:00:00Thursday | 2 | Time + day |
| 7Pm | 2 | Time only |
| 8Pm | 1 | Time only |
| Cancelled Due To Weather Forecast Alnwick Ford Bd | 1 | Status message |
| Concours D'Elegance Society Of Gb Membership 2025-26 | 1 | Event/membership name |
| Headley Heath Riders Association Annual Membership 2026 | 1 | Membership name |
| Laurelview - Please Book By Tues Night Latest | 1 | Instructions in venue |
| Laurelview- Younger Members From 6Pm... | 2 | Instructions in venue |
| Newsam Equestrian.This Covers The Practical Part... | 1 | Instructions in venue |
| Our Seniors Who Are Aged 17 And Over | 1 | Description |
| Ruth's. No Horses Required. 6.30 Start | 1 | Person name + instructions |
| Saturday And Sunday Postponded Until 21St | 1 | Status message |
| Sdrc Membership | 3 | Membership |
| Smiths Yard. Sorry Entries Are Already Full... | 5 | Apology in venue |
| Tbc, Tbc | 1 | Double placeholder |
| Asfr Regional Formation Riding Competition | 1 | Event name |
| Bd Scotland | 1 | Organisation name |
| Bs Scottish Committee | 1 | Organisation name |

**Action**: These indicate parser source data quality issues (primarily from Pony Club branch calendars). Consider adding normaliser guards for timestamps and common junk patterns.
