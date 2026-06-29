import Foundation

/// A single event as returned by `GET /api/competitions`.
///
/// Dates from the API come in two shapes (`date_start` is `YYYY-MM-DD`, the
/// `*_seen_at` timestamps are full ISO datetimes), so the day fields are decoded
/// as raw strings and parsed on demand — avoiding a global date strategy. The
/// `*_seen_at` timestamps aren't needed in the app, so they're simply ignored.
struct Competition: Identifiable, Codable, Sendable, Hashable {
    let id: Int
    let name: String
    let dateStart: String
    let dateEnd: String?
    let venueName: String
    let venuePostcode: String?
    let discipline: String?
    let latitude: Double?
    let longitude: Double?
    let distanceMiles: Double?
    let eventType: String
    let tags: [String]
    let url: String?

    enum CodingKeys: String, CodingKey {
        case id, name, discipline, latitude, longitude, tags, url
        case dateStart = "date_start"
        case dateEnd = "date_end"
        case venueName = "venue_name"
        case venuePostcode = "venue_postcode"
        case distanceMiles = "distance_miles"
        case eventType = "event_type"
    }

    var startDate: Date? { DayDate.parse(dateStart) }
    var endDate: Date? { dateEnd.flatMap(DayDate.parse) }

    /// Discipline tags only (e.g. ["discipline:dressage"]).
    var disciplineTags: [String] { tags.filter { $0.hasPrefix("discipline:") } }
    var affiliationTags: [String] { tags.filter { $0.hasPrefix("affiliation:") } }
}

/// Parsing + display helpers for the `YYYY-MM-DD` day strings.
enum DayDate {
    private static let parser: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "UTC")
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    static func parse(_ value: String) -> Date? { parser.date(from: value) }
}
