import CoreLocation
import Foundation
import Observation

/// Drives the Explore venue map. Shares the `FilterDriving` surface with the
/// events list so Compete/Watch/Explore use one filter bar. Defaults to "any
/// distance" so the map opens framing every venue (the nice world view); the
/// user narrows with the same pills, or the zoom-to-me map button.
@MainActor
@Observable
final class VenuesViewModel: FilterDriving {
    var venues: [VenueMarker] = []
    var isLoading = false
    var errorMessage: String?
    var filter = EventFilter()
    /// The postcode currently powering distance, for display.
    var activePostcode: String?
    var dateScope: DateScope = .upcoming
    var customDate: Date?
    /// nil == any distance; the map opens framing every venue.
    var radiusMiles: Double?
    var locationDenied = false

    /// Radius the zoom-to-me button frames when no distance filter is set.
    static let zoomDefaultRadiusMiles: Double = 30

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

    /// Disciplines present across the loaded venues, for the discipline pill.
    var availableDisciplines: [String] {
        Set(venues.flatMap(\.disciplines)).sorted()
    }

    // FilterDriving — the map opts out of the tier and venue pills.
    private(set) var series: String?
    private(set) var tier: String?
    var showsTier: Bool { false }
    var isWatch: Bool { false }
    var venueName: String? { nil }
    var discipline: String? { filter.discipline }
    var dateFilterActive: Bool { customDate != nil || dateScope != .upcoming }

    /// First appearance: acquire location (for distance) then load markers.
    func start() async {
        if !didStart {
            didStart = true
            await acquireLocation()
        }
        await load()
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            venues = try await api.venues(filter: filter)
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
        let bounds = scope.range()
        filter.dateFrom = bounds.from
        filter.dateTo = bounds.to
        await load()
    }

    func setCustomDate(_ date: Date) async {
        customDate = date
        let day = Calendar.current.startOfDay(for: date)
        filter.dateFrom = day
        filter.dateTo = day
        await load()
    }

    func setRadius(_ miles: Double?) async {
        radiusMiles = miles
        filter.maxDistance = miles
        if miles != nil && activePostcode == nil {
            await acquireLocation()
        }
        await load()
    }

    func retryLocation() async {
        await acquireLocation()
        await load()
    }

    /// No venue pin on the map itself.
    func clearVenue() async {}

    /// The device coordinate, for the zoom-to-me map button.
    func userCoordinate() async throws -> CLLocationCoordinate2D {
        try await location.currentCoordinate()
    }

    private func acquireLocation() async {
        do {
            let coord = try await location.currentCoordinate()
            let postcode = try await api.reverseGeocode(latitude: coord.latitude, longitude: coord.longitude)
            filter.postcode = postcode
            activePostcode = postcode
            locationDenied = false
        } catch {
            activePostcode = nil
            locationDenied = true
        }
    }
}
