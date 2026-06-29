import Foundation

/// Filters for the competitions list, mapped to the API's query parameters.
struct EventFilter: Equatable, Sendable {
    var discipline: String?
    var eventType: String?
    var spectator: Bool?
    var postcode: String?
    var maxDistance: Double?
    var dateFrom: Date?
    var dateTo: Date?
    /// Tag tokens to require, e.g. "affiliation:nsea", "series:trailblazers".
    var tags: [String] = []

    var queryItems: [URLQueryItem] {
        var items: [URLQueryItem] = []
        if let d = discipline, !d.isEmpty { items.append(.init(name: "discipline", value: d)) }
        for t in tags where !t.isEmpty { items.append(.init(name: "tag", value: t)) }
        if let t = eventType, !t.isEmpty { items.append(.init(name: "event_type", value: t)) }
        if let s = spectator { items.append(.init(name: "spectator", value: s ? "true" : "false")) }
        if let p = postcode, !p.isEmpty { items.append(.init(name: "postcode", value: p)) }
        if let m = maxDistance { items.append(.init(name: "max_distance", value: String(m))) }
        if let f = dateFrom { items.append(.init(name: "date_from", value: Self.day.string(from: f))) }
        if let t = dateTo { items.append(.init(name: "date_to", value: Self.day.string(from: t))) }
        return items
    }

    private static let day: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()
}

enum APIError: LocalizedError {
    case badStatus(Int)
    case invalidURL

    var errorDescription: String? {
        switch self {
        case .badStatus(let code): "The server returned an error (\(code))."
        case .invalidURL: "Could not build the request URL."
        }
    }
}

/// Reads events from the EquiCalendar backend. Stateless and `Sendable`.
struct APIClient: Sendable {
    var baseURL: URL = AppConfig.baseURL

    func competitions(filter: EventFilter = .init()) async throws -> [Competition] {
        let base = baseURL.appending(path: "api/competitions")
        guard var components = URLComponents(url: base, resolvingAgainstBaseURL: false) else {
            throw APIError.invalidURL
        }
        components.queryItems = filter.queryItems.isEmpty ? nil : filter.queryItems
        guard let url = components.url else { throw APIError.invalidURL }
        return try await get([Competition].self, from: url)
    }

    func competition(id: Int) async throws -> Competition {
        let url = baseURL.appending(path: "api/competitions/\(id)")
        return try await get(Competition.self, from: url)
    }

    func venues() async throws -> [VenueMarker] {
        let url = baseURL.appending(path: "api/venues/map")
        return try await get([VenueMarker].self, from: url)
    }

    /// Resolve a device coordinate to a UK postcode via the backend.
    func reverseGeocode(latitude: Double, longitude: Double) async throws -> String {
        let url = baseURL.appending(path: "api/geocode/reverse")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["lat": latitude, "lng": longitude])
        let (data, response) = try await URLSession.shared.data(for: request)
        if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            throw APIError.badStatus(http.statusCode)
        }
        struct ReverseResult: Decodable { let postcode: String }
        return try JSONDecoder().decode(ReverseResult.self, from: data).postcode
    }

    private func get<T: Decodable>(_ type: T.Type, from url: URL) async throws -> T {
        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await URLSession.shared.data(for: request)
        if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            throw APIError.badStatus(http.statusCode)
        }
        return try JSONDecoder().decode(T.self, from: data)
    }
}
