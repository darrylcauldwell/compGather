import CloudKit
import os
import SwiftUI
import UIKit

/// Wraps the system share/manage sheet for a CloudKit `CKShare`. Presenting this
/// with an existing share shows the "manage participants" UI; with a new one it
/// shows the invite UI. Permission is read-write so both people can edit.
///
/// The sheet itself is Apple's `UICloudSharingController` (fixed layout), but we
/// supply a title and a branded thumbnail via the delegate so its header shows
/// "EquiCalendar Plan" with the app's equestrian mark instead of a blank
/// document icon.
struct ShareContext: Identifiable {
    let id = UUID()
    let share: CKShare
    let container: CKContainer
}

struct CloudShareSheet: UIViewControllerRepresentable {
    let context: ShareContext

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIViewController(context: Context) -> UICloudSharingController {
        let controller = UICloudSharingController(share: self.context.share, container: self.context.container)
        controller.availablePermissions = [.allowReadWrite, .allowPrivate]
        controller.delegate = context.coordinator
        return controller
    }

    func updateUIViewController(_ controller: UICloudSharingController, context: Context) {}

    final class Coordinator: NSObject, UICloudSharingControllerDelegate {
        private let log = Logger(subsystem: "dev.dreamfold.equicalendar", category: "Share")

        func itemTitle(for csc: UICloudSharingController) -> String? { "EquiCalendar Plan" }

        func itemThumbnailData(for csc: UICloudSharingController) -> Data? {
            Self.thumbnail
        }

        func itemType(for csc: UICloudSharingController) -> String? { nil }

        func cloudSharingController(_ csc: UICloudSharingController, failedToSaveShareWithError error: Error) {
            log.error("Share save failed: \(error.localizedDescription, privacy: .public)")
        }

        /// Branded thumbnail: the app's accent colour with the equestrian mark,
        /// rendered once. Replaces `UICloudSharingController`'s generic document icon.
        private static let thumbnail: Data? = {
            let size = CGSize(width: 256, height: 256)
            let image = UIGraphicsImageRenderer(size: size).image { _ in
                (UIColor(named: "AccentColor") ?? .systemIndigo).setFill()
                UIBezierPath(roundedRect: CGRect(origin: .zero, size: size), cornerRadius: 56).fill()
                let config = UIImage.SymbolConfiguration(pointSize: 132, weight: .semibold)
                if let symbol = UIImage(systemName: "figure.equestrian.sports", withConfiguration: config)?
                    .withTintColor(.white, renderingMode: .alwaysOriginal) {
                    let s = symbol.size
                    symbol.draw(in: CGRect(
                        x: (size.width - s.width) / 2,
                        y: (size.height - s.height) / 2,
                        width: s.width, height: s.height
                    ))
                }
            }
            return image.pngData()
        }()
    }
}
