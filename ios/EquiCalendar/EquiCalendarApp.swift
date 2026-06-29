import SwiftData
import SwiftUI

@main
struct EquiCalendarApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
        }
        .modelContainer(for: Favourite.self)
    }
}
