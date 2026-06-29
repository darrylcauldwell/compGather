import SwiftUI

/// Root tab bar (iOS 26 Liquid Glass floating tabs).
struct RootView: View {
    var body: some View {
        TabView {
            Tab("Events", systemImage: "calendar") {
                EventsView(title: "Events", eventType: nil)
            }
            Tab("Shows", systemImage: "rosette") {
                EventsView(title: "Shows", eventType: "show")
            }
            Tab("Venues", systemImage: "map") {
                VenuesView()
            }
            Tab("Favourites", systemImage: "star") {
                FavouritesView()
            }
        }
    }
}
