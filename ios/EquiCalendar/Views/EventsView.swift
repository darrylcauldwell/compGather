import SwiftData
import SwiftUI

/// Browse upcoming events with discipline + "near me" filtering.
struct EventsView: View {
    @State private var model = EventsViewModel()
    @Query private var favourites: [Favourite]

    private var favouriteIDs: Set<Int> { Set(favourites.map(\.competitionId)) }

    var body: some View {
        NavigationStack {
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
            .safeAreaInset(edge: .top, spacing: 8) {
                VStack(spacing: 8) {
                    DisciplineChips(
                        disciplines: model.availableDisciplines,
                        selected: model.filter.discipline
                    ) { discipline in
                        Task { await model.setDiscipline(discipline) }
                    }
                    NearMeBar(
                        activePostcode: model.activePostcode,
                        onUseLocation: { Task { await model.useMyLocation() } },
                        onClear: { Task { await model.clearLocation() } }
                    )
                }
                .padding(.vertical, 8)
            }
            .navigationTitle("Events")
            .task { if model.events.isEmpty { await model.load() } }
        }
    }

    private var eventList: some View {
        List(model.events) { competition in
            NavigationLink(value: competition) {
                EventCard(competition: competition, isFavourite: favouriteIDs.contains(competition.id))
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
}
