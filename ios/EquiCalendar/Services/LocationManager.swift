import CoreLocation

/// One-shot device location for distance-based queries.
///
/// Only obtains the coordinate; reverse-geocoding to a UK postcode is done
/// server-side via `APIClient.reverseGeocode` (the device-side `CLGeocoder` is
/// deprecated on iOS 26 and the backend already resolves postcodes).
///
/// Shared across all view models (`.shared`) so the tabs don't each run their
/// own cold GPS fix. A recent cached fix answers instantly without touching
/// the radio; otherwise the first `CLLocationUpdate.liveUpdates()` fix wins,
/// falling back to a stale cached coordinate when the radio can't get a fix in
/// time — for sorting venues by distance, yesterday's coordinate still beats
/// failing. Concurrent callers share one in-flight request.
@MainActor
final class LocationManager {
    enum LocationError: Error { case denied, unavailable }

    static let shared = LocationManager()

    /// A fix younger than this answers a request without touching the radio.
    private static let freshFixMaxAge: TimeInterval = 5 * 60
    /// On timeout, fall back to a cached fix up to this old rather than fail.
    private static let staleFixMaxAge: TimeInterval = 24 * 3600
    /// How long to wait for a live fix (clock starts once any permission
    /// prompt has been answered).
    private static let fixTimeout: Duration = .seconds(30)

    private let manager = CLLocationManager()
    private var inflight: Task<CLLocationCoordinate2D, Error>?

    var isDenied: Bool {
        switch manager.authorizationStatus {
        case .denied, .restricted: true
        default: false
        }
    }

    /// Request the device location once, returning its coordinate.
    func currentCoordinate() async throws -> CLLocationCoordinate2D {
        if isDenied { throw LocationError.denied }
        if let cached = manager.location, Self.usable(cached, within: Self.freshFixMaxAge) {
            return cached.coordinate
        }
        if let inflight { return try await inflight.value }
        let task = Task { () throws -> CLLocationCoordinate2D in
            do {
                return try await Self.firstLiveFix()
            } catch LocationError.denied {
                throw LocationError.denied
            } catch {
                if let cached = self.manager.location,
                   Self.usable(cached, within: Self.staleFixMaxAge) {
                    return cached.coordinate
                }
                throw LocationError.unavailable
            }
        }
        inflight = task
        defer { inflight = nil }
        return try await task.value
    }

    /// First coordinate from the async updates stream, raced against a timeout.
    /// Starting the stream shows the When-In-Use prompt if authorization is
    /// undetermined; the timeout clock only starts once that's resolved, so a
    /// user reading the prompt can't time the request out.
    private nonisolated static func firstLiveFix() async throws -> CLLocationCoordinate2D {
        try await withThrowingTaskGroup(of: CLLocationCoordinate2D.self) { group in
            group.addTask {
                for try await update in CLLocationUpdate.liveUpdates() {
                    if update.authorizationDenied { throw LocationError.denied }
                    if let location = update.location { return location.coordinate }
                }
                throw LocationError.unavailable
            }
            group.addTask {
                let status = CLLocationManager()
                while status.authorizationStatus == .notDetermined {
                    try await Task.sleep(for: .milliseconds(500))
                }
                try await Task.sleep(for: fixTimeout)
                throw LocationError.unavailable
            }
            defer { group.cancelAll() }
            guard let first = try await group.next() else { throw LocationError.unavailable }
            return first
        }
    }

    /// Whether a cached fix is valid and young enough to stand in for a fresh one.
    nonisolated static func usable(_ location: CLLocation, within maxAge: TimeInterval,
                                   now: Date = .now) -> Bool {
        location.horizontalAccuracy >= 0 && now.timeIntervalSince(location.timestamp) < maxAge
    }
}
