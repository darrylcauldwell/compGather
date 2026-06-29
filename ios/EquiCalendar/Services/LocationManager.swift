import CoreLocation
import Observation

/// One-shot device location for distance-based queries.
///
/// Only obtains the coordinate; reverse-geocoding to a UK postcode is done
/// server-side via `APIClient.reverseGeocode` (the device-side `CLGeocoder` is
/// deprecated on iOS 26 and the backend already resolves postcodes).
@MainActor
@Observable
final class LocationManager: NSObject, CLLocationManagerDelegate {
    enum State: Equatable {
        case idle, requesting, resolved, denied, failed
    }

    private(set) var state: State = .idle
    private(set) var coordinate: CLLocationCoordinate2D?

    private let manager = CLLocationManager()
    private var continuation: CheckedContinuation<CLLocationCoordinate2D, Error>?

    enum LocationError: Error { case denied, failed }

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyKilometer
    }

    /// Request the device location once, returning its coordinate.
    func currentCoordinate() async throws -> CLLocationCoordinate2D {
        state = .requesting
        return try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
            switch manager.authorizationStatus {
            case .notDetermined:
                manager.requestWhenInUseAuthorization()
            case .authorizedWhenInUse, .authorizedAlways:
                manager.requestLocation()
            default:
                finish(.failure(LocationError.denied))
            }
        }
    }

    private func finish(_ result: Result<CLLocationCoordinate2D, Error>) {
        if case .failure(let error) = result {
            state = (error as? LocationError) == .denied ? .denied : .failed
        }
        continuation?.resume(with: result)
        continuation = nil
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        Task { @MainActor in
            switch status {
            case .authorizedWhenInUse, .authorizedAlways:
                if state == .requesting { self.manager.requestLocation() }
            case .denied, .restricted:
                finish(.failure(LocationError.denied))
            default:
                break
            }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let coordinate = locations.last?.coordinate else { return }
        Task { @MainActor in
            self.coordinate = coordinate
            state = .resolved
            finish(.success(coordinate))
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        Task { @MainActor in finish(.failure(LocationError.failed)) }
    }
}
