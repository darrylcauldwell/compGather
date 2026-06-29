import Foundation

/// App-wide configuration.
enum AppConfig {
    /// Base URL of the EquiCalendar backend the app reads from.
    ///
    /// Point this at your production EquiCalendar instance. For local
    /// development against the Docker stack use `http://localhost:8001`
    /// (and allow arbitrary loads in a debug build if needed).
    static let baseURL = URL(string: "https://equicalendar.dreamfold.dev")!
}
