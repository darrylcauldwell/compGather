import CoreData
import SwiftUI

/// Saved events ("Plan"), stored with Core Data + CloudKit so they sync across
/// the user's devices (and, in the sharing phase, with another person).
struct FavouritesView: View {
    @FetchRequest(sortDescriptors: [NSSortDescriptor(key: "dateStart", ascending: true)])
    private var favourites: FetchedResults<Favourite>

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
                        ForEach(favourites, id: \.objectID) { favourite in
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
        PlanStore.shared.delete(offsets.map { favourites[$0] })
    }
}

private struct FavouriteCard: View {
    @ObservedObject var favourite: Favourite

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(favourite.name ?? "")
                .font(AppTypography.cardTitle)
            Label(favourite.venueName ?? "", systemImage: "mappin.and.ellipse")
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
