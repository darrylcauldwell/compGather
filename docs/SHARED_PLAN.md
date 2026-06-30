# Shared Plan (CloudKit sharing) — v1.1 spec

**Status:** planned for v1.1 (after the v1.0 App Store launch). Not started.

## Goal
Let two people on **separate iPhones with different Apple IDs** share one Plan,
**both fully maintaining it** (collaborative read-write — either can add, remove,
and edit; it is NOT owner-writes / viewer-reads), synced live between both
devices. Each plan item also carries **notes** (and similar annotations) that
both can edit.

## Decision
Approach chosen (2026-06-30): **CloudKit sharing via `CKShare`** — native, free,
syncs directly between the two iPhones, no app-backend involvement. Rejected
alternatives: a backend share-code (more control but new server surface +
identity), and a shared calendar (no live in-app Plan — kept only as the
interim workaround, see below).

## The one big reality to design around
The Plan currently uses **SwiftData** (local-only `Favourite` model). SwiftData
gained CloudKit **private sync** (same Apple ID) but its support for **sharing
between different iCloud users** (`CKShare`) is immature as of 2026.

So the shared Plan should NOT rely on SwiftData sharing. Resolve at build time:
- **Option A (recommended):** move the `Favourite` store to **Core Data +
  `NSPersistentCloudKitContainer`**, which has mature share support
  (`UICloudSharingController`, shared zones, `share(_:to:)`). The rest of the app
  stays as-is.
- **Option B:** keep SwiftData for personal favourites and add a **thin raw
  CloudKit** layer (CKRecord + CKShare) just for the shared plan.

Option A is cleaner long-term (one store, real sharing); Option B avoids a
SwiftData→Core Data migration. Decide before phase 2.

## Data model (shared plan item)
The shared record is more than a bookmark — both participants annotate it:
- the event reference (competition id + denormalised name/venue/date so it
  survives even if the source event changes),
- **`notes`** — free text, editable by both (e.g. "aiming for the 90cm", travel
  plans, stabling booked),
- extensible annotations to add as needed: target **class/height**, a **status**
  (considering / entered / done), and optionally a **result**.

All fields are shared and last-write-wins via CloudKit (fine for two trusted
family members; no field-level merge needed). The current local-only `Favourite`
gains these fields too, so the model is consistent whether shared or not.

## Prerequisites
- Add **iCloud** capability + a CloudKit container
  `iCloud.dev.dreamfold.equicalendar` to the target (wire into `project.yml`
  entitlements/signing so it survives xcodegen).
- **Remote notifications** background mode (CloudKit uses silent pushes to sync).
- Both users signed into iCloud. Testing needs **two real devices + two Apple
  IDs** — CloudKit sharing can't be fully exercised in the simulator.

## UX
- Plan tab → **"Share Plan"** → `UICloudSharingController` → invite via Messages
  / link. Share permission is **read-write** (`.readWrite`) so both maintain it.
- Recipient opens the link → accepts the `CKShare` → the shared plan appears in
  their Plan tab.
- **Both** participants can add/remove events **and edit notes/annotations**;
  changes sync (seconds in foreground, next launch in background).
- Per-item **notes editor** in the Plan detail (and a notes preview on the card).
- Distinguish shared vs personal items (a "shared" badge or a separate section).
- Handle: stop sharing (owner), leave share (participant), offline edits (let
  CloudKit merge), and the not-on-iCloud case (Plan silently stays local).

## Implementation phases
1. Entitlements + container; prove **private** sync of favourites across two
   devices on one Apple ID.
2. Stand up the shared store (Option A or B) and `CKShare` plumbing.
3. Sharing UI + accept-share handling (`windowScene(_:userDidAcceptCloudKitShareWith:)`).
4. Merge/dedupe shared + local favourites; shared-item indicator in the Plan UI.
5. Two-device / two-account UAT.

## Acceptance criteria
- One shares Plan; the other accepts; both see the same events.
- **Either** participant add/remove/edits-notes on one device → reflected on the
  other (seconds foreground / next launch background). Both genuinely maintain it.
- Notes/annotations are editable by both and sync.
- No regression to the local-only Plan for users who never share.
- Graceful when a user isn't on iCloud (Plan stays local, no errors).

## Out of scope (this version)
- Backend-stored plans or user accounts.
- More than two participants (CKShare allows it; scope to parent↔child first).

## Interim workaround (available now, no build)
Add planned events to a **shared Apple/Google calendar** both subscribe to, via
the existing Add-to-Calendar / `.ics` export. Not a live in-app shared Plan, but
gives shared visibility today.
