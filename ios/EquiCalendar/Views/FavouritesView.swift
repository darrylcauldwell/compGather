import CoreData
import SwiftUI

/// Saved events ("Plan"), stored with Core Data + CloudKit so they sync across
/// the user's devices and can be shared, read-write, with another person.
///
/// The list of events is the focus. Sharing lives behind the toolbar cog
/// (`SharePlanSheet`) so the tab reads as a plan, not a share screen.
struct FavouritesView: View {
    @FetchRequest(sortDescriptors: [NSSortDescriptor(key: "dateStart", ascending: true)])
    private var favourites: FetchedResults<Favourite>

    @State private var showingSettings = false

    var body: some View {
        NavigationStack {
            content
                .navigationTitle("Plan")
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button {
                            showingSettings = true
                        } label: {
                            Label("Plan settings", systemImage: "gearshape")
                        }
                    }
                }
                .sheet(isPresented: $showingSettings) {
                    SharePlanSheet()
                }
        }
    }

    @ViewBuilder
    private var content: some View {
        if favourites.isEmpty {
            ContentUnavailableView {
                Label("Nothing planned yet", systemImage: "checklist")
            } description: {
                Text("Tap the star on an event to add it to your plan — saved for offline access.")
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
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
