import CoreData
import EventKit
import Foundation
import Testing
@testable import EquiCalendar

/// End-to-end check of Plan → Apple Calendar mirroring against the simulator's
/// real calendar database. Needs calendar access pre-granted to the host app
/// (`xcrun simctl privacy <device> grant calendar dev.dreamfold.equicalendar`);
/// without it the test skips rather than hanging on a permission prompt.
@MainActor
struct PlanCalendarSyncIntegrationTests {
    private static let testID: Int64 = 987_654_321

    @Test func mirrorsPlanIntoDedicatedCalendar() async throws {
        // Quiet no-op where access isn't pre-granted (fresh simulator/CI) —
        // requesting it here would hang the suite on the permission prompt.
        guard EKEventStore.authorizationStatus(for: .event) == .fullAccess else { return }

        let plan = try #require(PlanStore.shared.ensurePrivatePlan())
        let context = PlanStore.shared.viewContext
        removeTestFavourite(in: context)

        let favourite = Favourite(context: context)
        favourite.competitionId = Self.testID
        favourite.name = "Calendar Sync Test ODE"
        favourite.venueName = "Test Venue EC"
        favourite.discipline = "Eventing"
        favourite.dateStart = "2026-09-15"
        favourite.url = "https://equicalendar.dreamfold.dev"
        favourite.addedAt = .now
        favourite.plan = plan
        if let store = plan.objectID.persistentStore {
            context.assign(favourite, to: store)
        }
        try context.save()

        do {
            // Enable → the favourite should appear as an all-day event in the
            // app's own calendar.
            try await PlanCalendarSync.shared.setEnabled(true)
            let event = try #require(findTestEvent(), "favourite not mirrored to Apple Calendar")
            #expect(event.title == "Calendar Sync Test ODE")
            #expect(event.location == "Test Venue EC")
            #expect(event.isAllDay)
            #expect(event.calendar.title == "EquiCalendar Plan")

            // Un-favourite and resync → the event should be cleaned up.
            removeTestFavourite(in: context)
            try context.save()
            try await PlanCalendarSync.shared.setEnabled(true)
            #expect(findTestEvent() == nil, "removed favourite left a stale calendar event")

            // Toggle off → the whole calendar goes away.
            try await PlanCalendarSync.shared.setEnabled(false)
            let store = EKEventStore()
            #expect(!store.calendars(for: .event).contains { $0.title == "EquiCalendar Plan" })
        } catch {
            removeTestFavourite(in: context)
            try? context.save()
            try? await PlanCalendarSync.shared.setEnabled(false)
            throw error
        }
    }

    private func findTestEvent() -> EKEvent? {
        let store = EKEventStore()
        guard let calendar = store.calendars(for: .event)
            .first(where: { $0.title == "EquiCalendar Plan" }) else { return nil }
        let window = PlanCalendarSync.searchWindow()
        let predicate = store.predicateForEvents(
            withStart: window.start, end: window.end, calendars: [calendar]
        )
        return store.events(matching: predicate)
            .first { PlanCalendarSync.competitionID(inNotes: $0.notes) == Self.testID }
    }

    private func removeTestFavourite(in context: NSManagedObjectContext) {
        let request = Favourite.fetchRequest()
        request.predicate = NSPredicate(format: "competitionId == %lld", Self.testID)
        ((try? context.fetch(request)) ?? []).forEach(context.delete)
    }
}
