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
                Picker("Mode", selection: Binding(
                    get: { model.mode },
                    set: { newMode in Task { await model.setMode(newMode) } }
                )) {
                    ForEach(VenuesViewModel.ExploreMode.allCases) { mode in
                        Text(mode.title).tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)
                .padding(.top, 8)

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
                        ContentUnavailableView(
                            model.mode == .hire ? "No hire venues nearby" : "No venues match",
                            systemImage: model.mode == .hire ? "sportscourt" : "map"
                        )
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
                VenueCallout(venue: venue) {
                    router.venueRequest = .init(id: venue.id, name: venue.name)
                    router.selectedTab = .compete
                }
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
    /// Tapped via the prominent button below — opens this venue's events.
    let onViewEvents: () -> Void

    private var eventsText: String {
        "View \(venue.eventCount) event\(venue.eventCount == 1 ? "" : "s")"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(venue.name).font(AppTypography.cardTitle)
            if !venue.postcode.isEmpty {
                Label(venue.postcode, systemImage: "mappin.and.ellipse")
                    .font(AppTypography.cardMeta)
                    .foregroundStyle(.secondary)
            }
            if let hire = venue.hireURL, let url = URL(string: hire) {
                // Arena hire mode: we don't track availability — link out to enquire.
                Text("Offers arena hire — check availability with the venue.")
                    .font(AppTypography.cardMeta)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Link(destination: url) {
                    HStack(spacing: 6) {
                        Text("Check availability")
                        Image(systemName: "arrow.up.right.square")
                    }
                    .font(AppTypography.controlLabel)
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.glassProminent)
                .controlSize(.large)
                .accessibilityLabel("Check arena hire availability at \(venue.name)")
            } else {
                if !venue.disciplines.isEmpty {
                    Text(venue.disciplines.joined(separator: " · "))
                        .font(AppTypography.cardMeta)
                        .foregroundStyle(.tint)
                        .lineLimit(1)
                }
                // Clear, full-width call-to-action — a large, obvious tap target
                // instead of the easy-to-miss text link.
                Button(action: onViewEvents) {
                    HStack(spacing: 6) {
                        Text(eventsText)
                        Image(systemName: "arrow.right")
                    }
                    .font(AppTypography.controlLabel)
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.glassProminent)
                .controlSize(.large)
                .accessibilityLabel("View \(venue.eventCount) events at \(venue.name)")
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .glassEffect(.regular, in: .rect(cornerRadius: 20))
    }
}
