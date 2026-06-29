import Foundation
import Observation

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

    private let api: APIClient
    private let location: LocationManager

    init(api: APIClient = APIClient(), location: LocationManager = LocationManager()) {
        self.api = api
        self.location = location
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

    /// Use the device location: resolve a postcode, sort by distance, reload.
    func useMyLocation() async {
        isLoading = true
        errorMessage = nil
        do {
            let coord = try await location.currentCoordinate()
            let postcode = try await api.reverseGeocode(latitude: coord.latitude, longitude: coord.longitude)
            filter.postcode = postcode
            activePostcode = postcode
            await load()
        } catch {
            isLoading = false
            errorMessage = "Couldn't use your location. Check location permission in Settings."
        }
    }

    func clearLocation() async {
        filter.postcode = nil
        filter.maxDistance = nil
        activePostcode = nil
        await load()
    }
}
