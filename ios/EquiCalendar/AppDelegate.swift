import CloudKit
import UIKit

/// CloudKit share acceptance has no pure-SwiftUI entry point, so we bridge to a
/// scene delegate. The AppDelegate's only job is to route scene callbacks to
/// `SceneDelegate`; SwiftUI's `WindowGroup` still renders the UI.
final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        configurationForConnecting connectingSceneSession: UISceneSession,
        options: UIScene.ConnectionOptions
    ) -> UISceneConfiguration {
        let config = UISceneConfiguration(name: nil, sessionRole: connectingSceneSession.role)
        config.delegateClass = SceneDelegate.self
        return config
    }
}

final class SceneDelegate: NSObject, UIWindowSceneDelegate {
    /// App already running / suspended when the user taps a share link.
    func windowScene(
        _ windowScene: UIWindowScene,
        userDidAcceptCloudKitShareWith cloudKitShareMetadata: CKShare.Metadata
    ) {
        accept(cloudKitShareMetadata)
    }

    /// Cold launch from a share link.
    func scene(
        _ scene: UIScene,
        willConnectTo session: UISceneSession,
        options connectionOptions: UIScene.ConnectionOptions
    ) {
        if let metadata = connectionOptions.cloudKitShareMetadata {
            accept(metadata)
        }
    }

    private func accept(_ metadata: CKShare.Metadata) {
        Task { @MainActor in PlanStore.shared.accept(metadata) }
    }
}
