import CoreData
import EventKit
import os
import SwiftUI
import UIKit

/// Mirrors the Plan into a dedicated "EquiCalendar Plan" calendar in Apple
/// Calendar. Opt-in from the Plan settings sheet; needs full calendar access
/// (not the write-only grant used by the per-event Add to Calendar button) so
/// events can be updated and removed when the Plan changes.
///
/// The calendar is created in the user's iCloud source where available — so it
/// follows them to their other devices — falling back to a local calendar
/// otherwise. Events are matched to favourites by a `competitionId` marker in
/// the event notes, and each sync is a diff (create / update / delete) so
/// running it twice is a no-op.
@MainActor
final class PlanCalendarSync {
    static let shared = PlanCalendarSync()

    private nonisolated static let enabledKey = "plan_calendar_sync_enabled"
    private nonisolated static let calendarIDKey = "plan_calendar_identifier"
    private nonisolated static let calendarTitle = "EquiCalendar Plan"
    private nonisolated static let markerPrefix = "equicalendar-id:"

    private let store = EKEventStore()
    private let log = Logger(subsystem: "dev.dreamfold.equicalendar", category: "CalendarSync")
    private var observers: [NSObjectProtocol] = []
    private var pendingSync: Task<Void, Never>?

    enum SyncError: LocalizedError {
        case accessDenied
        case noSource

        var errorDescription: String? {
            switch self {
            case .accessDenied:
                "Calendar access was not granted. You can allow it in Settings → Apps → EquiCalendar → Calendars."
            case .noSource:
                "No calendar account is available to create the Plan calendar in."
            }
        }
    }

    var isEnabled: Bool { UserDefaults.standard.bool(forKey: Self.enabledKey) }

    /// Called once at launch: resume mirroring if the user previously enabled it.
    func startIfEnabled() {
        guard isEnabled else { return }
        guard EKEventStore.authorizationStatus(for: .event) == .fullAccess else {
            // Access was revoked in Settings since the toggle was turned on.
            UserDefaults.standard.set(false, forKey: Self.enabledKey)
            return
        }
        observePlanChanges()
        scheduleSync()
    }

    /// Turn mirroring on (requests full calendar access, then does a first
    /// sync) or off (removes the app's calendar — the user's own calendars are
    /// never touched).
    func setEnabled(_ on: Bool) async throws {
        if on {
            guard try await store.requestFullAccessToEvents() else {
                throw SyncError.accessDenied
            }
            UserDefaults.standard.set(true, forKey: Self.enabledKey)
            observePlanChanges()
            try syncNow()
        } else {
            UserDefaults.standard.set(false, forKey: Self.enabledKey)
            stopObserving()
            pendingSync?.cancel()
            removeCalendar()
        }
    }

    // MARK: - Sync

    /// Diff the favourites against the calendar's events: create what's
    /// missing, update what changed, delete what's no longer favourited.
    private func syncNow() throws {
        guard isEnabled else { return }
        let calendar = try ensureCalendar()

        let window = Self.searchWindow()
        let predicate = store.predicateForEvents(
            withStart: window.start, end: window.end, calendars: [calendar]
        )
        var eventsByID: [Int64: EKEvent] = [:]
        for event in store.events(matching: predicate) {
            guard let id = Self.competitionID(inNotes: event.notes) else { continue }
            eventsByID[id] = event
        }

        var dirty = false
        for favourite in fetchFavourites() {
            guard let start = favourite.startDate else { continue }
            let event = eventsByID.removeValue(forKey: favourite.competitionId)
                ?? EKEvent(eventStore: store)
            if apply(favourite, start: start, to: event, in: calendar) {
                try store.save(event, span: .thisEvent, commit: false)
                dirty = true
            }
        }
        // Whatever is left in the map has no matching favourite any more.
        for stale in eventsByID.values {
            try store.remove(stale, span: .thisEvent, commit: false)
            dirty = true
        }
        if dirty { try store.commit() }
    }

    /// Copy the favourite onto the event; returns whether anything changed so
    /// unchanged events are not re-saved (which would re-fire EKEventStoreChanged).
    private func apply(_ favourite: Favourite, start: Date, to event: EKEvent,
                       in calendar: EKCalendar) -> Bool {
        // All-day; EventKit treats the end as exclusive, so end on the next day.
        let end = Calendar.current.date(byAdding: .day, value: 1, to: start) ?? start
        let notes = [favourite.discipline, "\(Self.markerPrefix)\(favourite.competitionId)"]
            .compactMap { $0 }.joined(separator: "\n")
        let url = favourite.url.flatMap(URL.init(string:))

        var changed = false
        func set<T: Equatable>(_ keyPath: ReferenceWritableKeyPath<EKEvent, T>, _ value: T) {
            guard event[keyPath: keyPath] != value else { return }
            event[keyPath: keyPath] = value
            changed = true
        }
        if event.calendar != calendar { event.calendar = calendar; changed = true }
        set(\.title, favourite.name ?? "")
        set(\.location, favourite.venueName)
        set(\.isAllDay, true)
        set(\.startDate, start)
        set(\.endDate, end)
        set(\.url, url)
        set(\.notes, notes)
        return changed
    }

    /// All favourites across the private and shared stores, deduped by
    /// competitionId (the same event can exist in both during a share).
    private func fetchFavourites() -> [Favourite] {
        let all = (try? PlanStore.shared.viewContext.fetch(Favourite.fetchRequest())) ?? []
        var seen = Set<Int64>()
        return all.filter { seen.insert($0.competitionId).inserted }
    }

    /// Wide enough to clean up past plan events and cover anything plannable
    /// ahead; EventKit caps a single predicate at four years.
    nonisolated static func searchWindow(around now: Date = .now) -> (start: Date, end: Date) {
        let cal = Calendar.current
        return (cal.date(byAdding: .year, value: -2, to: now) ?? now,
                cal.date(byAdding: .year, value: 2, to: now) ?? now)
    }

    /// Parse the `competitionId` marker out of an event's notes. Events in the
    /// calendar without one (e.g. hand-added by the user) are left alone.
    nonisolated static func competitionID(inNotes notes: String?) -> Int64? {
        guard let notes else { return nil }
        for line in notes.split(separator: "\n") where line.hasPrefix(markerPrefix) {
            return Int64(line.dropFirst(markerPrefix.count))
        }
        return nil
    }

    // MARK: - The calendar itself

    /// Find the app's calendar, or (re)create it — also covers the user having
    /// deleted it from the Calendar app.
    private func ensureCalendar() throws -> EKCalendar {
        if let id = UserDefaults.standard.string(forKey: Self.calendarIDKey),
           let existing = store.calendar(withIdentifier: id) {
            return existing
        }
        // A calendar with our title can outlive a lost identifier (restore from
        // backup, reinstall) — adopt it rather than creating a duplicate.
        if let existing = store.calendars(for: .event)
            .first(where: { $0.title == Self.calendarTitle }) {
            UserDefaults.standard.set(existing.calendarIdentifier, forKey: Self.calendarIDKey)
            return existing
        }
        guard let source = iCloudSource ?? fallbackSource else { throw SyncError.noSource }
        let calendar = EKCalendar(for: .event, eventStore: store)
        calendar.title = Self.calendarTitle
        calendar.source = source
        calendar.cgColor = UIColor(Color.accentColor).cgColor
        try store.saveCalendar(calendar, commit: true)
        UserDefaults.standard.set(calendar.calendarIdentifier, forKey: Self.calendarIDKey)
        log.info("Created Plan calendar in source \(source.title, privacy: .public)")
        return calendar
    }

    /// iCloud where available, so the calendar syncs to the user's other devices.
    private var iCloudSource: EKSource? {
        store.sources.first {
            $0.sourceType == .calDAV && $0.title.localizedCaseInsensitiveContains("icloud")
        }
    }

    private var fallbackSource: EKSource? {
        store.defaultCalendarForNewEvents?.source
            ?? store.sources.first { $0.sourceType == .local }
    }

    private func removeCalendar() {
        defer { UserDefaults.standard.removeObject(forKey: Self.calendarIDKey) }
        guard let id = UserDefaults.standard.string(forKey: Self.calendarIDKey),
              let calendar = store.calendar(withIdentifier: id) else { return }
        do { try store.removeCalendar(calendar, commit: true) } catch {
            log.error("Couldn't remove Plan calendar: \(error.localizedDescription, privacy: .public)")
        }
    }

    // MARK: - Change observation

    /// Resync on: local Plan edits, CloudKit imports (a share partner's edits),
    /// and calendar-database changes (covers the user deleting our calendar —
    /// the next pass recreates it). Our own commits also fire the EventKit
    /// notification, but a resync of an already-synced plan writes nothing, so
    /// it converges instead of looping.
    private func observePlanChanges() {
        guard observers.isEmpty else { return }
        let center = NotificationCenter.default
        let sources: [(Notification.Name, Any?)] = [
            (.NSManagedObjectContextDidSave, PlanStore.shared.viewContext),
            (.NSPersistentStoreRemoteChange, PlanStore.shared.container.persistentStoreCoordinator),
            (.EKEventStoreChanged, store),
        ]
        for (name, object) in sources {
            observers.append(center.addObserver(
                forName: name, object: object, queue: .main
            ) { [weak self] _ in
                Task { @MainActor in self?.scheduleSync() }
            })
        }
    }

    private func stopObserving() {
        observers.forEach(NotificationCenter.default.removeObserver)
        observers.removeAll()
    }

    /// Debounced so bursts (e.g. a CloudKit import) collapse into one pass.
    private func scheduleSync() {
        pendingSync?.cancel()
        pendingSync = Task { @MainActor [weak self] in
            try? await Task.sleep(for: .seconds(1))
            guard !Task.isCancelled, let self else { return }
            do { try self.syncNow() } catch {
                self.log.error("Plan calendar sync failed: \(error.localizedDescription, privacy: .public)")
            }
        }
    }
}
