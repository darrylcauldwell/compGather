import CoreLocation
import Foundation

/// A venue marker for the Explore map. Decodes both `GET /api/venues/map`
/// (events mode — carries eventCount/disciplines) and `GET /api/venues/hire`
/// (Arena hire mode — carries a `hireURL` to enquire/book, no events).
struct VenueMarker: Identifiable, Codable, Sendable, Hashable {
    let id: Int
    let name: String
    let postcode: String
    let latitude: Double
    let longitude: Double
    let distanceMiles: Double?
    let eventCount: Int
    let disciplines: [String]
    /// Set only in Arena hire mode — a booking/enquiry link for the venue.
    let hireURL: String?

    enum CodingKeys: String, CodingKey {
        case id, name, postcode, disciplines
        case latitude = "lat"
        case longitude = "lng"
        case distanceMiles = "distance_miles"
        case eventCount = "event_count"
        case hireURL = "hire_url"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        name = try c.decode(String.self, forKey: .name)
        postcode = try c.decode(String.self, forKey: .postcode)
        latitude = try c.decode(Double.self, forKey: .latitude)
        longitude = try c.decode(Double.self, forKey: .longitude)
        distanceMiles = try c.decodeIfPresent(Double.self, forKey: .distanceMiles)
        eventCount = try c.decodeIfPresent(Int.self, forKey: .eventCount) ?? 0
        disciplines = try c.decodeIfPresent([String].self, forKey: .disciplines) ?? []
        let hire = try c.decodeIfPresent(String.self, forKey: .hireURL)
        hireURL = (hire?.isEmpty == false) ? hire : nil
    }

    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }
}
