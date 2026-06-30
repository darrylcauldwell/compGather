import SwiftUI

@main
struct EquiCalendarApp: App {
    // Bridges CloudKit share acceptance (scene-level) into the SwiftUI lifecycle.
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            RootView()
        }
        // Plan is now Core Data + CloudKit (see PlanStore). Inject the view
        // context so @FetchRequest in the Plan/event views reads it.
        .environment(\.managedObjectContext, PlanStore.shared.viewContext)
    }
}
