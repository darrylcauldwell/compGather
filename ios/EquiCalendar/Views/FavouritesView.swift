import CloudKit
import CoreData
import os
import SwiftUI

/// Saved events ("Plan"), stored with Core Data + CloudKit so they sync across
/// the user's devices and can be shared, read-write, with another person.
struct FavouritesView: View {
    @FetchRequest(sortDescriptors: [NSSortDescriptor(key: "dateStart", ascending: true)])
    private var favourites: FetchedResults<Favourite>

    @State private var shareContext: ShareContext?
    @State private var canShare = false
    @State private var shareError: String?
    @State private var isPreparingShare = false

    private let log = Logger(subsystem: "dev.dreamfold.equicalendar", category: "Share")

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
            .toolbar {
                if canShare {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button {
                            Task { await startShare() }
                        } label: {
                            Label("Share Plan", systemImage: "person.crop.circle.badge.plus")
                        }
                        .disabled(isPreparingShare)
                    }
                }
            }
            .task { canShare = await PlanStore.shared.iCloudAvailable() }
            .sheet(item: $shareContext) { context in
                CloudShareSheet(context: context)
            }
            .alert("Couldn't share Plan", isPresented: .init(
                get: { shareError != nil },
                set: { if !$0 { shareError = nil } }
            )) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(shareError ?? "")
            }
        }
    }

    private func delete(at offsets: IndexSet) {
        PlanStore.shared.delete(offsets.map { favourites[$0] })
    }

    private func startShare() async {
        isPreparingShare = true
        defer { isPreparingShare = false }
        do {
            let (share, container) = try await PlanStore.shared.makeShare()
            shareContext = ShareContext(share: share, container: container)
        } catch {
            log.error("Share prepare failed: \(error.localizedDescription, privacy: .public)")
            shareError = error.localizedDescription
        }
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
