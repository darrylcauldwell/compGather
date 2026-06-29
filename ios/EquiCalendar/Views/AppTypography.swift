import SwiftUI

/// Central typography for the app. Views must reference these tokens rather than
/// inline `.font(...)` literals. Uses dynamic type styles so text scales with
/// the user's system text size.
enum AppTypography {
    static let screenTitle: Font = .largeTitle.weight(.bold)
    static let sectionTitle: Font = .title3.weight(.semibold)
    static let cardTitle: Font = .headline
    static let cardBody: Font = .subheadline
    static let cardMeta: Font = .caption
    static let badge: Font = .caption2.weight(.semibold)
    static let controlLabel: Font = .callout.weight(.medium)
    static let toast: Font = .callout
}
