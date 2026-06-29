import SwiftUI

/// Root tab bar (iOS 26 Liquid Glass floating tabs).
struct RootView: View {
    var body: some View {
        TabView {
            Tab("Compete", systemImage: "flag.checkered") {
                EventsView(title: "Compete", eventType: nil)
            }
            Tab("Watch", systemImage: "binoculars") {
                EventsView(title: "Watch", spectator: true)
            }
            Tab("Explore", systemImage: "map") {
                VenuesView()
            }
            Tab("Plan", systemImage: "checklist") {
                FavouritesView()
            }
        }
    }
}
