import Observation

/// Cross-tab navigation state. A `TabView` selection alone can't carry a payload
/// between tabs, so this lets the Explore map hand a tapped venue to the Compete
/// tab: set `selectedTab` and `venueRequest`, and the Compete list consumes it.
@MainActor
@Observable
final class AppRouter {
    enum Tab: Hashable { case compete, prepare, watch, explore, plan }

    var selectedTab: Tab = .compete

    /// Set when a venue pin is tapped; the Compete list applies then clears it.
    var venueRequest: VenueRequest?

    struct VenueRequest: Equatable {
        let id: Int
        let name: String
    }
}
