import MapKit
import SwiftUI

/// A map of venues that have upcoming events. Tapping a pin shows a glass
/// callout with the venue's event count and disciplines.
struct VenuesView: View {
    @State private var venues: [VenueMarker] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var selectedID: Int?
    @State private var camera: MapCameraPosition = .automatic

    private let api = APIClient()

    private var selectedVenue: VenueMarker? {
        venues.first { $0.id == selectedID }
    }

    var body: some View {
        NavigationStack {
            Group {
                if isLoading && venues.isEmpty {
                    ProgressView("Loading venues…")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let errorMessage, venues.isEmpty {
                    ContentUnavailableView {
                        Label("Couldn't load venues", systemImage: "map")
                    } description: {
                        Text(errorMessage)
                    } actions: {
                        Button("Try Again") { Task { await load() } }
                            .buttonStyle(.glassProminent)
                    }
                } else {
                    map
                }
            }
            .navigationTitle("Explore")
            .navigationBarTitleDisplayMode(.inline)
            .task { if venues.isEmpty { await load() } }
        }
    }

    private var map: some View {
        Map(position: $camera, selection: $selectedID) {
            ForEach(venues) { venue in
                Marker(venue.name, systemImage: "figure.equestrian.sports", coordinate: venue.coordinate)
                    .tag(venue.id)
            }
        }
        .overlay(alignment: .bottom) {
            if let venue = selectedVenue {
                VenueCallout(venue: venue)
                    .padding()
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.snappy, value: selectedID)
    }

    private func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            venues = try await api.venues()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct VenueCallout: View {
    let venue: VenueMarker

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(venue.name).font(AppTypography.cardTitle)
            if !venue.postcode.isEmpty {
                Label(venue.postcode, systemImage: "mappin.and.ellipse")
                    .font(AppTypography.cardMeta)
                    .foregroundStyle(.secondary)
            }
            Label(
                "\(venue.eventCount) upcoming event\(venue.eventCount == 1 ? "" : "s")",
                systemImage: "calendar"
            )
            .font(AppTypography.cardMeta)
            .foregroundStyle(.secondary)
            if !venue.disciplines.isEmpty {
                Text(venue.disciplines.joined(separator: " · "))
                    .font(AppTypography.cardMeta)
                    .foregroundStyle(.tint)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .glassEffect(.regular, in: .rect(cornerRadius: 20))
    }
}
