import CloudKit
import SwiftUI
import UIKit

/// Wraps the system share/manage sheet for a CloudKit `CKShare`. Presenting this
/// with an existing share shows the "manage participants" UI; with a new one it
/// shows the invite UI. Permission is read-write so both people can edit.
struct ShareContext: Identifiable {
    let id = UUID()
    let share: CKShare
    let container: CKContainer
}

struct CloudShareSheet: UIViewControllerRepresentable {
    let context: ShareContext

    func makeUIViewController(context: Context) -> UICloudSharingController {
        let controller = UICloudSharingController(share: self.context.share, container: self.context.container)
        controller.availablePermissions = [.allowReadWrite, .allowPrivate]
        return controller
    }

    func updateUIViewController(_ controller: UICloudSharingController, context: Context) {}
}
