import SwiftUI

/// Formats an event's date range for display: "18 Jun 2026" (single day),
/// "16–18 Jun 2026" (same month) or "28 Jun – 2 Jul 2026" (spanning months).
enum EventFormatting {
    private static let display: DateFormatter = {
        let f = DateFormatter(); f.locale = .current
        f.setLocalizedDateFormatFromTemplate("d MMM yyyy"); return f
    }()
    private static let dayMonth: DateFormatter = {
        let f = DateFormatter(); f.locale = .current
        f.setLocalizedDateFormatFromTemplate("d MMM"); return f
    }()
    private static let dayOnly: DateFormatter = {
        let f = DateFormatter(); f.locale = .current
        f.setLocalizedDateFormatFromTemplate("d"); return f
    }()

    static func dateText(start: Date?, end: Date?) -> String {
        guard let start else { return "" }
        guard let end, end != start else { return display.string(from: start) }
        if Calendar.current.isDate(start, equalTo: end, toGranularity: .month) {
            return "\(dayOnly.string(from: start))–\(display.string(from: end))"
        }
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
///
/// Meta is laid out on separate rows (venue + distance share a row) so long
/// names, date ranges, and disciplines never wrap awkwardly.
struct EventCard: View {
    let competition: Competition
    var isFavourite: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
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
            .padding(.bottom, 2)

            // Venue (left, truncates) + distance (right) on one row.
            HStack(spacing: 8) {
                Label(competition.venueName, systemImage: "mappin.and.ellipse")
                    .lineLimit(1)
                    .truncationMode(.tail)
                if let distance = competition.distanceMiles {
                    Spacer(minLength: 8)
                    Label("\(Int(distance.rounded())) mi", systemImage: "location.fill")
                        .lineLimit(1)
                        .layoutPriority(1)
                }
            }
            .font(AppTypography.cardMeta)
            .foregroundStyle(.secondary)

            // Date on its own row.
            Label(
                EventFormatting.dateText(start: competition.startDate, end: competition.endDate),
                systemImage: "calendar"
            )
            .font(AppTypography.cardMeta)
            .foregroundStyle(.secondary)
            .lineLimit(1)

            // Discipline(s) on their own row — multi-discipline fixtures list all.
            if !competition.disciplineNames.isEmpty {
                Label(competition.disciplineNames.joined(separator: " · "), systemImage: "figure.equestrian.sports")
                    .font(AppTypography.cardMeta)
                    .foregroundStyle(.tint)
                    .lineLimit(2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .glassEffect(.regular, in: .rect(cornerRadius: 20))
    }
}
