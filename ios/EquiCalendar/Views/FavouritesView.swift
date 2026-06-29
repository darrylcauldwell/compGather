import SwiftData
import SwiftUI

/// Saved events, stored locally with SwiftData so they're available offline.
struct FavouritesView: View {
    @Environment(\.modelContext) private var modelContext
    @Query(sort: \Favourite.dateStart) private var favourites: [Favourite]

    var body: some View {
        NavigationStack {
            Group {
                if favourites.isEmpty {
                    ContentUnavailableView {
                        Label("Nothing planned yet", systemImage: "checklist")
                    } description: {
                        Text("Tap the star on an event to add it to your plan — saved for offline access.")
                    }
                } else {
                    List {
                        ForEach(favourites) { favourite in
                            FavouriteCard(favourite: favourite)
                                .listRowSeparator(.hidden)
                                .listRowBackground(Color.clear)
                                .listRowInsets(.init(top: 6, leading: 16, bottom: 6, trailing: 16))
                        }
                        .onDelete(perform: delete)
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("Plan")
        }
    }

    private func delete(at offsets: IndexSet) {
        for index in offsets { modelContext.delete(favourites[index]) }
        try? modelContext.save()
    }
}

private struct FavouriteCard: View {
    let favourite: Favourite

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(favourite.name)
                .font(AppTypography.cardTitle)
            Label(favourite.venueName, systemImage: "mappin.and.ellipse")
                .font(AppTypography.cardBody)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            HStack(spacing: 8) {
                TagBadge(
                    text: EventFormatting.dateText(start: favourite.startDate, end: nil),
                    systemImage: "calendar",
                    tint: .primary
                )
                if let discipline = favourite.discipline {
                    TagBadge(text: discipline, systemImage: "figure.equestrian.sports", tint: .accentColor)
                }
            }
            if let urlString = favourite.url, let url = URL(string: urlString) {
                Link(destination: url) {
                    Label("View on organiser site", systemImage: "safari")
                        .font(AppTypography.cardMeta)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .glassEffect(.regular, in: .rect(cornerRadius: 20))
    }
}
