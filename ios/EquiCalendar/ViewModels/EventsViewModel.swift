import Foundation
import Observation

/// A date window for the events list, with friendly quick options.
enum DateScope: String, CaseIterable, Identifiable {
    case upcoming, today, thisWeekend, thisWeek, thisMonth

    var id: String { rawValue }

    var title: String {
        switch self {
        case .upcoming: "Upcoming"
        case .today: "Today"
        case .thisWeekend: "This Weekend"
        case .thisWeek: "This Week"
        case .thisMonth: "This Month"
        }
    }

    /// The (from, to) day bounds for this scope. `nil` `to` means open-ended.
    func range(calendar: Calendar = .current, now: Date = .now) -> (from: Date?, to: Date?) {
        let today = calendar.startOfDay(for: now)
        switch self {
        case .upcoming:
            return (today, nil)
        case .today:
            return (today, today)
        case .thisWeekend:
            let weekday = calendar.component(.weekday, from: today)  // 1 = Sun … 7 = Sat
            if weekday == 1 { return (today, today) }                // Sunday: weekend ends today
            let daysUntilSat = (7 - weekday) % 7
            let sat = calendar.date(byAdding: .day, value: daysUntilSat, to: today) ?? today
            let sun = calendar.date(byAdding: .day, value: 1, to: sat) ?? sat
            return (sat, sun)
        case .thisWeek:
            let end = calendar.dateInterval(of: .weekOfYear, for: today)
                .flatMap { calendar.date(byAdding: .day, value: -1, to: $0.end) }
            return (today, end)
        case .thisMonth:
            let end = calendar.dateInterval(of: .month, for: today)
                .flatMap { calendar.date(byAdding: .day, value: -1, to: $0.end) }
            return (today, end)
        }
    }
}

/// Distance radius options (miles). `nil` == any distance.
let radiusOptions: [Double] = [10, 25, 30, 50, 100]

/// Drives the events list: holds the current filter, loads from the API, and
/// resolves "near me" via the device location + server reverse-geocode.
@MainActor
@Observable
final class EventsViewModel {
    var events: [Competition] = []
    var isLoading = false
    var errorMessage: String?
    var filter = EventFilter()
    /// The postcode currently powering distance sorting, for display.
    var activePostcode: String?
    var dateScope: DateScope = .upcoming
    /// A specific chosen day; when set it overrides `dateScope`.
    var customDate: Date?
    /// Selected radius in miles; nil == any distance. Defaults to 30 on launch.
    var radiusMiles: Double? = defaultRadiusMiles
    /// True if the device location was requested but unavailable/denied.
    var locationDenied = false

    static let defaultRadiusMiles: Double = 30

    private let api: APIClient
    private let location: LocationManager
    private var didStart = false

    init(api: APIClient = APIClient(), location: LocationManager = LocationManager()) {
        self.api = api
        self.location = location
        let bounds = DateScope.upcoming.range()
        filter.dateFrom = bounds.from
        filter.dateTo = bounds.to
    }

    /// All distinct disciplines present in the loaded events, for the filter UI.
    var availableDisciplines: [String] {
        Set(events.compactMap(\.discipline)).sorted()
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            events = try await api.competitions(filter: filter)
        } catch is CancellationError {
            // ignore
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func setDiscipline(_ discipline: String?) async {
        filter.discipline = discipline
        await load()
    }

    func setDateScope(_ scope: DateScope) async {
        dateScope = scope
        customDate = nil
        let bounds = scope.range()
        filter.dateFrom = bounds.from
        filter.dateTo = bounds.to
        await load()
    }

    /// Filter to a single specific day.
    func setCustomDate(_ date: Date) async {
        customDate = date
        let day = Calendar.current.startOfDay(for: date)
        filter.dateFrom = day
        filter.dateTo = day
        await load()
    }

    /// True if any non-default date filter is active.
    var dateFilterActive: Bool { customDate != nil || dateScope != .upcoming }

    /// First appearance: auto-acquire location, apply the default radius, load.
    func start() async {
        if !didStart {
            didStart = true
            filter.maxDistance = radiusMiles
            await acquireLocation()
        }
        await load()
    }

    /// Change the distance radius (nil == any). Acquires location on demand.
    func setRadius(_ miles: Double?) async {
        radiusMiles = miles
        filter.maxDistance = miles
        if miles != nil && activePostcode == nil {
            await acquireLocation()
        }
        await load()
    }

    /// Best-effort device location → postcode (server-side reverse geocode).
    private func acquireLocation() async {
        do {
            let coord = try await location.currentCoordinate()
            let postcode = try await api.reverseGeocode(latitude: coord.latitude, longitude: coord.longitude)
            filter.postcode = postcode
            activePostcode = postcode
            locationDenied = false
        } catch {
            // No location: the distance filter is inert without a postcode, so
            // all events still show. Flag it for the UI.
            activePostcode = nil
            locationDenied = true
        }
    }
}
