import SwiftUI

/// Root tab bar (iOS 26 Liquid Glass floating tabs).
struct RootView: View {
    var body: some View {
        TabView {
            Tab("Events", systemImage: "calendar") {
                EventsView()
            }
            Tab("Favourites", systemImage: "star") {
                FavouritesView()
            }
        }
    }
}
