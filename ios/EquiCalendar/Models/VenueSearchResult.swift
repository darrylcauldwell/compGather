import Foundation

/// A venue matching the picker's search text (`GET /api/venues/search`).
/// Only venues with upcoming events are returned, busiest first.
struct VenueSearchResult: Identifiable, Codable, Sendable, Hashable {
    let id: Int
    let name: String
    let postcode: String
    let eventCount: Int

    enum CodingKeys: String, CodingKey {
        case id, name, postcode
        case eventCount = "event_count"
    }
}
