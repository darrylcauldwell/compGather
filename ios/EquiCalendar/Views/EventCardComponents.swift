import SwiftUI

/// Formats an event's date range for display, e.g. "15 Mar" or "15–18 Mar 2026".
enum EventFormatting {
    private static let display: DateFormatter = {
        let f = DateFormatter()
        f.locale = .current
        f.setLocalizedDateFormatFromTemplate("d MMM yyyy")
        return f
    }()

    private static let dayMonth: DateFormatter = {
        let f = DateFormatter()
        f.locale = .current
        f.setLocalizedDateFormatFromTemplate("d MMM")
        return f
    }()

    static func dateText(start: Date?, end: Date?) -> String {
        guard let start else { return "" }
        guard let end, end != start else { return display.string(from: start) }
        return "\(dayMonth.string(from: start)) – \(display.string(from: end))"
    }
}

/// A small Liquid Glass pill, used for discipline/affiliation/distance chips.
struct TagBadge: View {
    let text: String
    var systemImage: String?
    var tint: Color = .secondary

    var body: some View {
        Label {
            Text(text).font(AppTypography.badge)
        } icon: {
            if let systemImage { Image(systemName: systemImage) }
        }
        .labelStyle(.titleAndIcon)
        .foregroundStyle(tint)
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .glassEffect(.regular, in: .capsule)
    }
}

/// A single event rendered as a floating Liquid Glass card.
struct EventCard: View {
    let competition: Competition
    var isFavourite: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                Text(competition.name)
                    .font(AppTypography.cardTitle)
                    .foregroundStyle(.primary)
                Spacer(minLength: 8)
                if isFavourite {
                    Image(systemName: "star.fill")
                        .foregroundStyle(.yellow)
                        .font(AppTypography.cardMeta)
                }
            }

            Label(competition.venueName, systemImage: "mappin.and.ellipse")
                .font(AppTypography.cardBody)
                .foregroundStyle(.secondary)
                .lineLimit(1)

            HStack(spacing: 8) {
                TagBadge(
                    text: EventFormatting.dateText(start: competition.startDate, end: competition.endDate),
                    systemImage: "calendar",
                    tint: .primary
                )
                if let discipline = competition.discipline {
                    TagBadge(text: discipline, systemImage: "figure.equestrian.sports", tint: .accentColor)
                }
                if let distance = competition.distanceMiles {
                    TagBadge(text: "\(Int(distance.rounded())) mi", systemImage: "location.fill", tint: .secondary)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .glassEffect(.regular, in: .rect(cornerRadius: 20))
    }
}
