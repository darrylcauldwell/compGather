import CoreLocation
import Observation

/// One-shot device location for distance-based queries.
///
/// Only obtains the coordinate; reverse-geocoding to a UK postcode is done
/// server-side via `APIClient.reverseGeocode` (the device-side `CLGeocoder` is
/// deprecated on iOS 26 and the backend already resolves postcodes).
///
/// Uses `startUpdatingLocation` and waits for the first good fix (with a
/// timeout) rather than the one-shot `requestLocation`, which frequently fails
/// with a transient "location unknown" error right after launch.
@MainActor
@Observable
final class LocationManager: NSObject, CLLocationManagerDelegate {
    enum LocationError: Error { case denied, unavailable }

    private let manager = CLLocationManager()
    private var continuation: CheckedContinuation<CLLocationCoordinate2D, Error>?
    private var timeoutTask: Task<Void, Never>?

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyKilometer
    }

    var isDenied: Bool {
        switch manager.authorizationStatus {
        case .denied, .restricted: true
        default: false
        }
    }

    /// Request the device location once, returning its coordinate.
    func currentCoordinate() async throws -> CLLocationCoordinate2D {
        if isDenied { throw LocationError.denied }
        return try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
            timeoutTask = Task { @MainActor in
                try? await Task.sleep(for: .seconds(10))
                resume(.failure(LocationError.unavailable))
            }
            switch manager.authorizationStatus {
            case .notDetermined:
                manager.requestWhenInUseAuthorization()  // prompt, then start in didChange
            default:
                manager.startUpdatingLocation()
            }
        }
    }

    private func resume(_ result: Result<CLLocationCoordinate2D, Error>) {
        guard let continuation else { return }
        self.continuation = nil
        timeoutTask?.cancel()
        timeoutTask = nil
        manager.stopUpdatingLocation()
        continuation.resume(with: result)
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        Task { @MainActor in
            guard continuation != nil else { return }
            switch status {
            case .authorizedWhenInUse, .authorizedAlways:
                self.manager.startUpdatingLocation()
            case .denied, .restricted:
                resume(.failure(LocationError.denied))
            default:
                break  // still undetermined — keep waiting for the prompt result
            }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let coordinate = locations.last?.coordinate else { return }
        Task { @MainActor in resume(.success(coordinate)) }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        // "Location unknown" is transient — keep waiting for the next update.
        if (error as? CLError)?.code == .locationUnknown { return }
        Task { @MainActor in resume(.failure(LocationError.unavailable)) }
    }
}
