import CoreLocation
import Foundation

/// A venue with upcoming events, from `GET /api/venues/map`.
struct VenueMarker: Identifiable, Codable, Sendable, Hashable {
    let id: Int
    let name: String
    let postcode: String
    let latitude: Double
    let longitude: Double
    let distanceMiles: Double?
    let eventCount: Int
    let disciplines: [String]

    enum CodingKeys: String, CodingKey {
        case id, name, postcode, disciplines
        case latitude = "lat"
        case longitude = "lng"
        case distanceMiles = "distance_miles"
        case eventCount = "event_count"
    }

    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }
}
