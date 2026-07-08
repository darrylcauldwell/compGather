import SwiftUI

/// Search venues by name or postcode and pin the events list to one — the
/// same state the Explore map's "All events" hand-off produces. Opened from
/// the filter bar's "Any venue" pill.
struct VenueSearchSheet: View {
    /// Called with the chosen venue; the sheet dismisses itself.
    let onPick: (VenueSearchResult) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var results: [VenueSearchResult] = []
    @State private var isSearching = false
    @State private var errorMessage: String?
    @State private var searchTask: Task<Void, Never>?

    private let api = APIClient()

    var body: some View {
        NavigationStack {
            content
                .navigationTitle("Find a Venue")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } }
                }
                .searchable(
                    text: $query,
                    placement: .navigationBarDrawer(displayMode: .always),
                    prompt: "Venue name or postcode"
                )
                .onChange(of: query) { _, text in
                    scheduleSearch(for: text)
                }
        }
    }

    @ViewBuilder
    private var content: some View {
        if query.trimmingCharacters(in: .whitespaces).count < 2 {
            ContentUnavailableView {
                Label("Search venues", systemImage: "mappin.and.ellipse")
            } description: {
                Text("Type a venue name or postcode to see its upcoming events.")
            }
        } else if let errorMessage {
            ContentUnavailableView {
                Label("Search failed", systemImage: "wifi.exclamationmark")
            } description: {
                Text(errorMessage)
            } actions: {
                Button("Try again") { scheduleSearch(for: query) }
            }
        } else if results.isEmpty && !isSearching {
            ContentUnavailableView.search(text: query)
        } else {
            List(results) { venue in
                Button {
                    onPick(venue)
                    dismiss()
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(venue.name)
                            .font(AppTypography.cardBody)
                            .foregroundStyle(.primary)
                        Text(subtitle(for: venue))
                            .font(AppTypography.cardMeta)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .listStyle(.plain)
            .overlay(alignment: .top) {
                if isSearching { ProgressView().padding() }
            }
        }
    }

    private func subtitle(for venue: VenueSearchResult) -> String {
        let events = "\(venue.eventCount) upcoming event\(venue.eventCount == 1 ? "" : "s")"
        return venue.postcode.isEmpty ? events : "\(venue.postcode) · \(events)"
    }

    /// Debounced live search: waits for a typing pause, cancels stale requests.
    private func scheduleSearch(for text: String) {
        searchTask?.cancel()
        errorMessage = nil
        let term = text.trimmingCharacters(in: .whitespaces)
        guard term.count >= 2 else {
            results = []
            isSearching = false
            return
        }
        isSearching = true
        searchTask = Task {
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            do {
                let found = try await api.searchVenues(query: term)
                guard !Task.isCancelled else { return }
                results = found
            } catch is CancellationError {
                return
            } catch {
                results = []
                errorMessage = error.localizedDescription
            }
            isSearching = false
        }
    }
}
