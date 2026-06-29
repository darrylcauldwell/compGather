import EventKit
import Foundation

/// Adds events to the user's calendar via EventKit (write-only access, iOS 17+).
enum CalendarService {
    enum CalendarError: LocalizedError {
        case accessDenied
        case noDate

        var errorDescription: String? {
            switch self {
            case .accessDenied: "Calendar access was not granted."
            case .noDate: "This event has no usable date."
            }
        }
    }

    static func add(_ competition: Competition) async throws {
        let store = EKEventStore()
        let granted = try await store.requestWriteOnlyAccessToEvents()
        guard granted else { throw CalendarError.accessDenied }
        guard let start = competition.startDate else { throw CalendarError.noDate }

        let event = EKEvent(eventStore: store)
        event.title = competition.name
        event.location = competition.venueName
        event.isAllDay = true
        event.startDate = start
        // EventKit treats the end of an all-day event as exclusive; use the day
        // after the last day so multi-day events span correctly.
        let lastDay = competition.endDate ?? start
        event.endDate = Calendar.current.date(byAdding: .day, value: 1, to: lastDay) ?? lastDay
        if let urlString = competition.url, let url = URL(string: urlString) {
            event.url = url
        }
        event.notes = competition.discipline
        event.calendar = store.defaultCalendarForNewEvents
        try store.save(event, span: .thisEvent, commit: true)
    }
}
