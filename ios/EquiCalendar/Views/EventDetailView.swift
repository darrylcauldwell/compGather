import MapKit
import SwiftData
import SwiftUI

/// Event detail: map, key facts, favourite toggle, add-to-calendar, source link.
struct EventDetailView: View {
    let competition: Competition

    @Environment(\.modelContext) private var modelContext
    @Environment(\.openURL) private var openURL
    @Query private var favourites: [Favourite]

    @State private var calendarMessage: String?
    @State private var isAddingToCalendar = false

    private var favourite: Favourite? {
        favourites.first { $0.competitionId == competition.id }
    }
    private var isFavourite: Bool { favourite != nil }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let coordinate = coordinate {
                    Button { openInMaps() } label: {
                        Map(initialPosition: .region(region(coordinate))) {
                            Marker(competition.venueName, coordinate: coordinate)
                        }
                        .frame(height: 200)
                        .clipShape(.rect(cornerRadius: 20))
                        .allowsHitTesting(false)
                        .overlay(alignment: .bottomTrailing) {
                            Label("Maps", systemImage: "arrow.up.forward.app")
                                .font(AppTypography.badge)
                                .padding(.horizontal, 10).padding(.vertical, 6)
                                .glassEffect(.regular, in: .capsule)
                                .padding(10)
                        }
                    }
                    .buttonStyle(.plain)
                }

                Text(competition.name)
                    .font(AppTypography.sectionTitle)

                if let description = competition.description, !description.isEmpty {
                    Text(description)
                        .font(AppTypography.cardBody)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                factsCard

                if !competition.classes.isEmpty {
                    classesCard
                }

                if !competition.tags.isEmpty {
                    badges
                }

                actions

                if let calendarMessage {
                    Text(calendarMessage)
                        .font(AppTypography.toast)
                        .foregroundStyle(.secondary)
                }
            }
            .padding()
        }
        .navigationTitle("Event")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    toggleFavourite()
                } label: {
                    Image(systemName: isFavourite ? "star.fill" : "star")
                        .foregroundStyle(isFavourite ? .yellow : .accentColor)
                }
                .accessibilityLabel(isFavourite ? "Remove favourite" : "Add favourite")
            }
        }
    }

    private var factsCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            detailRow("calendar", EventFormatting.dateText(start: competition.startDate, end: competition.endDate))
            detailRow("mappin.and.ellipse", competition.venueName)
            if let postcode = competition.venuePostcode {
                detailRow("number", postcode)
            }
            if let discipline = competition.discipline {
                detailRow("figure.equestrian.sports", discipline)
            }
            if let distance = competition.distanceMiles {
                detailRow("location.fill", "\(Int(distance.rounded())) miles away")
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .glassEffect(.regular, in: .rect(cornerRadius: 20))
    }

    private var classesCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Classes")
                .font(AppTypography.cardMeta)
                .foregroundStyle(.secondary)
            ForEach(competition.classes, id: \.self) { cls in
                Label(cls, systemImage: "list.bullet")
                    .font(AppTypography.cardBody)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .glassEffect(.regular, in: .rect(cornerRadius: 20))
    }

    private func detailRow(_ icon: String, _ text: String) -> some View {
        Label(text, systemImage: icon)
            .font(AppTypography.cardBody)
            .foregroundStyle(.primary)
    }

    private var badges: some View {
        GlassEffectContainer(spacing: 8) {
            HStack(spacing: 8) {
                ForEach(competition.affiliationTags, id: \.self) { tag in
                    TagBadge(text: displayName(for: tag), systemImage: "rosette", tint: .accentColor)
                }
            }
        }
    }

    private var actions: some View {
        VStack(spacing: 12) {
            Button {
                addToCalendar()
            } label: {
                Label("Add to Calendar", systemImage: "calendar.badge.plus")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.glassProminent)
            .disabled(isAddingToCalendar)

            // Only offer "Open in Apple Maps" when we have coordinates to drop a
            // pin — matching the map preview above. Without a location it would
            // open Maps to nothing, which is confusing.
            if coordinate != nil {
                Button { openInMaps() } label: {
                    Label("Open in Apple Maps", systemImage: "map")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.glass)
            }

            if let urlString = competition.url, let url = URL(string: urlString) {
                Link(destination: url) {
                    Label("View on organiser site", systemImage: "safari")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.glass)
            }
        }
    }

    // MARK: - Helpers

    private var coordinate: CLLocationCoordinate2D? {
        guard let lat = competition.latitude, let lon = competition.longitude else { return nil }
        return CLLocationCoordinate2D(latitude: lat, longitude: lon)
    }

    /// Open the venue in Apple Maps: a dropped pin if we have coordinates,
    /// otherwise a search for the venue name + postcode (works for every event).
    private func openInMaps() {
        var components = URLComponents(string: "https://maps.apple.com/")!
        if let lat = competition.latitude, let lng = competition.longitude {
            components.queryItems = [
                .init(name: "ll", value: "\(lat),\(lng)"),
                .init(name: "q", value: competition.venueName),
            ]
        } else {
            let query = [competition.venueName, competition.venuePostcode]
                .compactMap { $0 }.joined(separator: " ")
            components.queryItems = [.init(name: "q", value: query)]
        }
        if let url = components.url { openURL(url) }
    }

    private func region(_ coordinate: CLLocationCoordinate2D) -> MKCoordinateRegion {
        MKCoordinateRegion(center: coordinate, latitudinalMeters: 6000, longitudinalMeters: 6000)
    }

    private func displayName(for tag: String) -> String {
        tag.split(separator: ":").last.map { $0.replacingOccurrences(of: "-", with: " ").capitalized } ?? tag
    }

    private func toggleFavourite() {
        if let favourite {
            modelContext.delete(favourite)
        } else {
            modelContext.insert(Favourite(competition))
        }
        try? modelContext.save()
    }

    private func addToCalendar() {
        isAddingToCalendar = true
        Task {
            defer { isAddingToCalendar = false }
            do {
                try await CalendarService.add(competition)
                calendarMessage = "Added to your calendar."
            } catch {
                calendarMessage = error.localizedDescription
            }
        }
    }
}
