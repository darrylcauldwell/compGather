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
    /// Monospaced style for raw URLs / share links (dynamic type doesn't suit a
    /// single-line link field). Justified fixed-style exception.
    static let linkMono: Font = .footnote.monospaced()
    /// Decorative hero SF Symbol size for empty/onboarding cards (fixed, like
    /// canvas glyphs — not body text, so it doesn't scale with dynamic type).
    static let heroSymbol: Font = .system(size: 44)
}
