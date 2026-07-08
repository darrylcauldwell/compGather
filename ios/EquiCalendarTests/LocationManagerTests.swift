import CoreLocation
import Foundation
import Testing
@testable import EquiCalendar

struct LocationManagerTests {
    private let now = Date(timeIntervalSince1970: 1_780_000_000)

    private func fix(ageSeconds: TimeInterval, accuracy: CLLocationAccuracy = 50) -> CLLocation {
        CLLocation(
            coordinate: CLLocationCoordinate2D(latitude: 54.5, longitude: -1.6),
            altitude: 0, horizontalAccuracy: accuracy, verticalAccuracy: 0,
            timestamp: now.addingTimeInterval(-ageSeconds)
        )
    }

    @Test func freshFixIsUsable() {
        #expect(LocationManager.usable(fix(ageSeconds: 60), within: 300, now: now))
    }

    @Test func expiredFixIsNotUsable() {
        #expect(!LocationManager.usable(fix(ageSeconds: 600), within: 300, now: now))
    }

    @Test func staleWindowAcceptsAnOldFix() {
        #expect(LocationManager.usable(fix(ageSeconds: 6 * 3600), within: 24 * 3600, now: now))
    }

    @Test func invalidAccuracyIsNeverUsable() {
        #expect(!LocationManager.usable(fix(ageSeconds: 60, accuracy: -1), within: 300, now: now))
    }
}
