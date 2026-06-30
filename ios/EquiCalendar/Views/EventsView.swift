import SwiftData
import SwiftUI

/// Browse events with discipline / date / distance filtering. Reused for the
/// Events tab (competitions) and the Shows tab (`eventType: "show"`).
struct EventsView: View {
    let title: String
    /// Only the Compete tab listens for venue hand-offs from the Explore map.
    let respondsToVenueRouting: Bool
    @State private var model: EventsViewModel
    @Environment(AppRouter.self) private var router
    @Environment(\.modelContext) private var modelContext
    @Query private var favourites: [Favourite]

    init(title: String = "Events", eventType: String? = nil, spectator: Bool? = nil, respondsToVenueRouting: Bool = false) {
        self.title = title
        self.respondsToVenueRouting = respondsToVenueRouting
        _model = State(initialValue: EventsViewModel(baseEventType: eventType, baseSpectator: spectator))
    }

    private var favouriteIDs: Set<Int> { Set(favourites.map(\.competitionId)) }

    var body: some View {
        NavigationStack {
            // FilterBar is a normal sibling above the list (not a safeAreaInset
            // overlay) so menu taps can't fall through to the list rows beneath.
            VStack(spacing: 0) {
                FilterBar(model: model)
                    .padding(.vertical, 8)
                Divider()

                Group {
                    if model.isLoading && model.events.isEmpty {
                        ProgressView("Loading events…")
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else if let error = model.errorMessage, model.events.isEmpty {
                        ContentUnavailableView {
                            Label("Couldn't load events", systemImage: "wifi.exclamationmark")
                        } description: {
                            Text(error)
                        } actions: {
                            Button("Try Again") { Task { await model.load() } }
                                .buttonStyle(.glassProminent)
                        }
                    } else if model.events.isEmpty {
                        ContentUnavailableView("No events found", systemImage: "calendar")
                    } else {
                        eventList
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .task {
                await model.start()
                // Consume any venue hand-off queued while this tab was backgrounded
                // (onChange below only fires when the tab is already foreground).
                await applyPendingVenue()
            }
            .onChange(of: router.venueRequest) { _, request in
                guard request != nil else { return }
                Task { await applyPendingVenue() }
            }
        }
    }

    private var eventList: some View {
        List(model.events) { competition in
            NavigationLink(value: competition) {
                EventCard(
                    competition: competition,
                    isFavourite: favouriteIDs.contains(competition.id),
                    onToggleFavourite: { toggleFavourite(competition) }
                )
            }
            .listRowSeparator(.hidden)
            .listRowBackground(Color.clear)
            .listRowInsets(.init(top: 6, leading: 16, bottom: 6, trailing: 16))
        }
        .listStyle(.plain)
        .navigationDestination(for: Competition.self) { competition in
            EventDetailView(competition: competition)
        }
        .refreshable { await model.load() }
    }

    /// Apply a venue hand-off from the Explore map, if one is pending. Runs both
    /// on appear (covers a hand-off that arrived while this tab was backgrounded)
    /// and on change (covers the foreground case). Runs after start() so its
    /// venue-filtered load isn't overwritten by the default load.
    private func applyPendingVenue() async {
        guard respondsToVenueRouting, let request = router.venueRequest else { return }
        await model.applyVenue(id: request.id, name: request.name)
        router.venueRequest = nil
    }

    /// Add/remove the event from Plan straight from the list (mirrors the detail view).
    private func toggleFavourite(_ competition: Competition) {
        if let existing = favourites.first(where: { $0.competitionId == competition.id }) {
            modelContext.delete(existing)
        } else {
            modelContext.insert(Favourite(competition))
        }
        try? modelContext.save()
    }
}
