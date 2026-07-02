import SwiftUI

/// Root tab bar (iOS 26 Liquid Glass floating tabs).
struct RootView: View {
    @State private var router = AppRouter()

    var body: some View {
        TabView(selection: $router.selectedTab) {
            Tab("Compete", systemImage: "flag.checkered", value: AppRouter.Tab.compete) {
                EventsView(title: "Compete", eventType: nil, respondsToVenueRouting: true)
            }
            Tab("Prepare", systemImage: "graduationcap", value: AppRouter.Tab.prepare) {
                EventsView(title: "Prepare", eventType: "training")
            }
            Tab("Watch", systemImage: "binoculars", value: AppRouter.Tab.watch) {
                EventsView(title: "Watch", spectator: true)
            }
            Tab("Explore", systemImage: "map", value: AppRouter.Tab.explore) {
                VenuesView()
            }
            Tab("Plan", systemImage: "checklist", value: AppRouter.Tab.plan) {
                FavouritesView()
            }
        }
        .environment(router)
    }
}
