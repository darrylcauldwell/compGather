import MapKit
import SwiftUI

/// A map of venues that have upcoming events, sharing the events filter bar.
/// Tapping a pin shows a glass callout; tapping the callout hands the venue to
/// the Compete tab (switch tab + pre-filter to that venue's events).
struct VenuesView: View {
    @State private var model = VenuesViewModel()
    @Environment(AppRouter.self) private var router
    @State private var selectedID: Int?
    @State private var camera: MapCameraPosition = .automatic

    private var selectedVenue: VenueMarker? {
        model.venues.first { $0.id == selectedID }
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                FilterBar(model: model)
                    .padding(.vertical, 8)
                Divider()

                Group {
                    if model.isLoading && model.venues.isEmpty {
                        ProgressView("Loading venues…")
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else if let errorMessage = model.errorMessage, model.venues.isEmpty {
                        ContentUnavailableView {
                            Label("Couldn't load venues", systemImage: "map")
                        } description: {
                            Text(errorMessage)
                        } actions: {
                            Button("Try Again") { Task { await model.load() } }
                                .buttonStyle(.glassProminent)
                        }
                    } else if model.venues.isEmpty {
                        ContentUnavailableView("No venues match", systemImage: "map")
                    } else {
                        map
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .navigationTitle("Explore")
            .navigationBarTitleDisplayMode(.inline)
            .task { await model.start() }
        }
    }

    private var map: some View {
        Map(position: $camera, selection: $selectedID) {
            UserAnnotation()
            ForEach(model.venues) { venue in
                Marker(venue.name, systemImage: "figure.equestrian.sports", coordinate: venue.coordinate)
                    .tag(venue.id)
            }
        }
        .overlay(alignment: .topTrailing) {
            Button {
                Task { await zoomToUser() }
            } label: {
                Image(systemName: "location.fill")
                    .font(.title3)
                    .padding(10)
            }
            .buttonStyle(.glass)
            .padding()
        }
        .overlay(alignment: .bottom) {
            if let venue = selectedVenue {
                Button {
                    router.venueRequest = .init(id: venue.id, name: venue.name)
                    router.selectedTab = .compete
                } label: {
                    VenueCallout(venue: venue)
                }
                .buttonStyle(.plain)
                .padding()
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.snappy, value: selectedID)
    }

    /// Centre the map on the device location at the current radius (default 30 mi).
    private func zoomToUser() async {
        guard let coord = try? await model.userCoordinate() else { return }
        let radiusMeters = (model.radiusMiles ?? VenuesViewModel.zoomDefaultRadiusMiles) * 1609.34
        withAnimation {
            camera = .region(MKCoordinateRegion(
                center: coord,
                latitudinalMeters: radiusMeters * 2,
                longitudinalMeters: radiusMeters * 2
            ))
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
            HStack(spacing: 4) {
                Text("View events")
                Image(systemName: "chevron.right")
            }
            .font(AppTypography.cardMeta)
            .foregroundStyle(.tint)
            .padding(.top, 2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .glassEffect(.regular, in: .rect(cornerRadius: 20))
    }
}
