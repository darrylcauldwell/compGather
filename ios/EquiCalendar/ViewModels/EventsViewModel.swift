import CoreLocation
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

/// An amateur competition pathway the user can filter to. `id` is the tag token
/// matched server-side; `name` is the display label. Slice 1 uses pathways that
/// are already tagged in the data; more (Trailblazers, Cricklands…) follow once
/// the `series:` tags ship.
struct SeriesOption: Identifiable, Sendable {
    let id: String   // tag token, e.g. "affiliation:nsea"
    let name: String
}

let seriesOptions: [SeriesOption] = [
    // Pinnacle finals to aim a season at (curated)
    .init(id: "special:championship-final", name: "🏆 Championships & Finals"),
    // Affiliation pathways (source-tagged)
    .init(id: "affiliation:nsea", name: "NSEA"),
    .init(id: "affiliation:pony-club", name: "Pony Club"),
    .init(id: "affiliation:bsps", name: "BSPS"),
    // Named unaffiliated series (text/class detected)
    .init(id: "series:trailblazers", name: "Trailblazers"),
    .init(id: "series:cricklands", name: "Cricklands"),
    .init(id: "series:bs-club", name: "BS Club"),
    .init(id: "series:blue-chip", name: "Blue Chip"),
    // BS classes (BS vocabulary; "Pony" = the junior tier)
    .init(id: "audience:pony", name: "Pony classes"),
    .init(id: "class:pony-foxhunter", name: "Pony Foxhunter"),
    .init(id: "class:pony-newcomers", name: "Pony Newcomers"),
    .init(id: "class:foxhunter", name: "Foxhunter"),
    .init(id: "class:newcomers", name: "Newcomers"),
    .init(id: "class:british-novice", name: "British Novice"),
]

/// Compete "Level" filter options (the affiliation ladder).
let levelOptions: [SeriesOption] = [
    .init(id: "tier:unaffiliated", name: "Unaffiliated"),
    .init(id: "tier:affiliated", name: "Affiliated"),
    .init(id: "tier:elite", name: "Elite"),
]

/// Watch "Type" filter options (spectator categories).
let watchTypeOptions: [SeriesOption] = [
    .init(id: "tier:elite", name: "Elite"),
    .init(id: "tier:county-show", name: "County Show"),
    .init(id: "tier:national", name: "National"),
]

/// Drives the events list: holds the current filter, loads from the API, and
/// resolves "near me" via the device location + server reverse-geocode.
@MainActor
@Observable
final class EventsViewModel: FilterDriving {
    var events: [Competition] = []
    var isLoading = false
    var errorMessage: String?
    var filter = EventFilter()
    /// The postcode currently powering distance sorting, for display.
    var activePostcode: String?
    var dateScope: DateScope = .upcoming
    /// A specific chosen day; when set it overrides `dateScope`.
    var customDate: Date?
    /// End of a custom date range; nil when filtering a single day.
    var customDateEnd: Date?
    /// Selected radius in miles; nil == any distance. Defaults to 30 on launch.
    var radiusMiles: Double? = defaultRadiusMiles
    /// True if the device location was requested but unavailable/denied.
    var locationDenied = false
    /// Name of the venue this list is pinned to (via a map hand-off), or nil.
    var venueName: String?

    static let defaultRadiusMiles: Double = 30

    private let api: APIClient
    private let location: LocationManager
    private var didStart = false
    /// When the list last fetched successfully; bounds tab-switch refetches.
    private var lastLoaded: Date?
    /// Re-appearing within this window keeps the current list untouched.
    private static let freshnessWindow: TimeInterval = 5 * 60

    init(
        api: APIClient = APIClient(),
        location: LocationManager = .shared,
        baseEventType: String? = nil,
        baseSpectator: Bool? = nil
    ) {
        self.api = api
        self.location = location
        filter.eventType = baseEventType
        filter.spectator = baseSpectator
        // Watch events are elite/destination fixtures — mostly continental, so a
        // local radius would hide them. Default Watch to "any distance" (still
        // distance-sorted); Compete keeps the local 30-mile default.
        radiusMiles = baseSpectator == true ? nil : Self.defaultRadiusMiles
        let bounds = DateScope.upcoming.range()
        filter.dateFrom = bounds.from
        filter.dateTo = bounds.to
    }

    /// All distinct disciplines present in the loaded events, for the filter UI.
    var availableDisciplines: [String] {
        Set(events.compactMap(\.discipline)).sorted()
    }

    /// Current discipline filter (FilterDriving surface).
    var discipline: String? { filter.discipline }

    /// Compete shows Series + the Level tier pill; Watch drops both (amateur
    /// pathways don't apply to spectating) and instead surfaces a Championships
    /// toggle for the big fixtures worth watching.
    var showsTier: Bool { !isWatch && !isTraining }
    var showsSeries: Bool { !isWatch && !isTraining }
    var showsChampionships: Bool { isWatch }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        // No resolved postcode makes the distance filter inert — the server
        // ignores max_distance (so far-away events leak in) and annotates no
        // distances. Re-acquire on every load so a transient reverse-geocode
        // failure heals on the next refresh, unless location is denied or the
        // list is pinned to a venue (where distance doesn't apply).
        if activePostcode == nil, !locationDenied, filter.venueID == nil {
            await acquireLocation()
        }
        do {
            events = try await api.competitions(filter: filter)
            lastLoaded = .now
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

    /// Selected filter tags, tracked per axis and combined into filter.tags (AND).
    private(set) var series: String?   // series:/affiliation:/class: token
    private(set) var tier: String?     // tier: token (Level / Watch Type)

    /// True on the Watch tab — drives the Level-vs-Type menu.
    var isWatch: Bool { filter.spectator == true }

    /// True on the Prepare tab — clinics/training have no amateur series or
    /// affiliation level ladder, so those pills are hidden (Discipline + Date only).
    var isTraining: Bool { filter.eventType == "training" }

    // "Hide Pony Club" — Prepare only. Most PC prepare events are members-only,
    // so a non-PC rider can filter them out (excludes affiliation:pony-club).
    var showsPonyClubFilter: Bool { isTraining }
    var hidePonyClub: Bool { filter.excludeTags.contains("affiliation:pony-club") }
    func setHidePonyClub(_ hide: Bool) async {
        filter.excludeTags = hide ? ["affiliation:pony-club"] : []
        await load()
    }

    func setSeries(_ token: String?) async {
        series = token
        rebuildTags()
        await load()
    }

    func setTier(_ token: String?) async {
        tier = token
        rebuildTags()
        await load()
    }

    private func rebuildTags() {
        filter.tags = [series, tier].compactMap { $0 }
    }

    func setDateScope(_ scope: DateScope) async {
        dateScope = scope
        customDate = nil
        customDateEnd = nil
        let bounds = scope.range()
        filter.dateFrom = bounds.from
        filter.dateTo = bounds.to
        await load()
    }

    /// Filter to a specific day or an inclusive range of days.
    func setCustomDates(from start: Date, to end: Date) async {
        let calendar = Calendar.current
        let from = calendar.startOfDay(for: min(start, end))
        let to = calendar.startOfDay(for: max(start, end))
        customDate = from
        customDateEnd = to == from ? nil : to
        filter.dateFrom = from
        filter.dateTo = to
        await load()
    }

    /// True if any non-default date filter is active.
    var dateFilterActive: Bool { customDate != nil || dateScope != .upcoming }

    /// First appearance: apply the default radius and load — load() acquires
    /// the device location as part of every fetch. Re-appearance (tab switch)
    /// skips the refetch while the list is fresh — pull-to-refresh and every
    /// filter change call load() directly, so those always hit the network.
    func start() async {
        if !didStart {
            didStart = true
            filter.maxDistance = radiusMiles
        }
        if let lastLoaded, Date.now.timeIntervalSince(lastLoaded) < Self.freshnessWindow {
            return
        }
        await load()
    }

    /// Change the distance radius (nil == any). load() acquires location on
    /// demand when none is resolved yet.
    func setRadius(_ miles: Double?) async {
        radiusMiles = miles
        filter.maxDistance = miles
        await load()
    }

    /// Re-attempt location (after the user enables it / taps Try again).
    func retryLocation() async {
        await acquireLocation()
        await load()
    }

    /// Pin the list to a single venue (a map pin handed off to Compete). The
    /// distance radius is cleared so a far-away venue's events aren't filtered
    /// out — the whole point is to show everything on at that venue.
    func applyVenue(id: Int, name: String) async {
        filter.venueID = id
        venueName = name
        radiusMiles = nil
        filter.maxDistance = nil
        await load()
    }

    /// Remove the venue pin and return to the normal filtered list.
    func clearVenue() async {
        guard filter.venueID != nil else { return }
        filter.venueID = nil
        venueName = nil
        await load()
    }

    /// Best-effort device location → postcode (server-side reverse geocode).
    private func acquireLocation() async {
        let coord: CLLocationCoordinate2D
        do {
            coord = try await location.currentCoordinate()
            locationDenied = false
        } catch {
            // No location: the distance filter is inert without a postcode, so
            // all events still show. Flag it for the UI.
            activePostcode = nil
            locationDenied = true
            return
        }
        do {
            let postcode = try await api.reverseGeocode(latitude: coord.latitude, longitude: coord.longitude)
            filter.postcode = postcode
            activePostcode = postcode
        } catch {
            // The fix succeeded but the reverse-geocode call failed (patchy
            // signal, server unreachable) — that's not a location problem, so
            // don't claim "Location off"; "Try again" re-runs just this.
            activePostcode = nil
        }
    }
}
