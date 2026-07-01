import SwiftUI
import UIKit

/// Discoverable filter bar: labelled Liquid Glass pills that open menus for
/// discipline, date scope, location, and distance radius. Each pill shows the
/// current selection so the active filters are always visible.
struct FilterBar<Model: FilterDriving>: View {
    let model: Model

    @State private var showDatePicker = false
    @State private var pickedDate = Date()

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            GlassEffectContainer(spacing: 8) {
                HStack(spacing: 8) {
                    if let venue = model.venueName {
                        venuePill(venue)
                    }
                    if model.showsSeries {
                        seriesMenu
                    }
                    if model.showsTier {
                        tierMenu
                    }
                    if model.showsChampionships {
                        championshipsPill
                    }
                    if model.showsDiscipline {
                        disciplineMenu
                    }
                    if model.showsDate {
                        dateMenu
                    }
                    distanceMenu
                }
                .padding(.horizontal)
            }
        }
        .sheet(isPresented: $showDatePicker) {
            DatePickerSheet(initialDate: model.customDate ?? Date()) { chosen in
                Task { await model.setCustomDate(chosen) }
            }
            .presentationDetents([.medium])
        }
    }

    /// Shown when the list is pinned to a venue (map hand-off); tap to clear.
    private func venuePill(_ name: String) -> some View {
        Button {
            Task { await model.clearVenue() }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "mappin.circle.fill")
                Text(name).font(AppTypography.controlLabel).lineLimit(1)
                Image(systemName: "xmark.circle.fill").font(.caption2)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .foregroundStyle(Color.white)
            .glassEffect(.regular.tint(.accentColor).interactive(), in: .capsule)
        }
        .buttonStyle(.plain)
    }

    /// Filter to an amateur pathway (NSEA, Pony Club, BSPS…). Composes with the
    /// distance radius, so "NSEA within 50 miles" is just this + the distance pill.
    private var seriesMenu: some View {
        Menu {
            menuItem("All series", selected: model.series == nil) {
                Task { await model.setSeries(nil) }
            }
            ForEach(seriesOptions) { option in
                menuItem(option.name, selected: model.series == option.id) {
                    Task { await model.setSeries(option.id) }
                }
            }
        } label: {
            pill(seriesLabel, icon: "rosette", active: model.series != nil)
        }
    }

    private var seriesLabel: String {
        guard let token = model.series else { return "All series" }
        return seriesOptions.first { $0.id == token }?.name ?? "Series"
    }

    /// Compete shows a "Level" filter (Unaffiliated/Affiliated/Elite); Watch
    /// shows a "Type" filter (Elite/County Show/National). Both filter on tier:.
    private var tierMenu: some View {
        let options = model.isWatch ? watchTypeOptions : levelOptions
        let label = model.isWatch ? "Type" : "Level"
        return Menu {
            menuItem("All \(label.lowercased())s", selected: model.tier == nil) {
                Task { await model.setTier(nil) }
            }
            ForEach(options) { option in
                menuItem(option.name, selected: model.tier == option.id) {
                    Task { await model.setTier(option.id) }
                }
            }
        } label: {
            pill(options.first { $0.id == model.tier }?.name ?? label,
                 icon: model.isWatch ? "binoculars" : "chart.bar.fill",
                 active: model.tier != nil)
        }
    }

    /// Watch-only toggle for championship/final fixtures. Uses the series slot,
    /// which carries the special:championship-final tag.
    private var championshipsPill: some View {
        let active = model.series == championshipToken
        return Button {
            Task { await model.setSeries(active ? nil : championshipToken) }
        } label: {
            pill("Championships", icon: "trophy.fill", active: active, showsChevron: false)
        }
    }

    private var championshipToken: String { "special:championship-final" }

    private var disciplineMenu: some View {
        Menu {
            menuItem("All disciplines", selected: model.discipline == nil) {
                Task { await model.setDiscipline(nil) }
            }
            ForEach(model.availableDisciplines, id: \.self) { discipline in
                menuItem(discipline, selected: model.discipline == discipline) {
                    Task { await model.setDiscipline(discipline) }
                }
            }
        } label: {
            pill(model.discipline ?? "All disciplines",
                 icon: "figure.equestrian.sports",
                 active: model.discipline != nil)
        }
    }

    private var dateMenu: some View {
        Menu {
            ForEach(DateScope.allCases) { scope in
                menuItem(scope.title, selected: model.customDate == nil && model.dateScope == scope) {
                    Task { await model.setDateScope(scope) }
                }
            }
            Divider()
            Button("Pick a date…", systemImage: "calendar") {
                pickedDate = model.customDate ?? Date()
                showDatePicker = true
            }
        } label: {
            pill(dateLabel, icon: "calendar", active: model.dateFilterActive)
        }
    }

    private var dateLabel: String {
        if let date = model.customDate {
            return EventFormatting.dateText(start: date, end: nil)
        }
        return model.dateScope.title
    }

    /// Distance dropdown (like the website): auto-uses the device location and
    /// defaults to 30 mi; pick another radius or "Any distance".
    private var distanceMenu: some View {
        Menu {
            if model.locationDenied {
                Button("Try again", systemImage: "arrow.clockwise") {
                    Task { await model.retryLocation() }
                }
                Button("Open Settings", systemImage: "gear") {
                    if let url = URL(string: UIApplication.openSettingsURLString) {
                        UIApplication.shared.open(url)
                    }
                }
                Divider()
            }
            menuItem("Any distance", selected: model.radiusMiles == nil) {
                Task { await model.setRadius(nil) }
            }
            ForEach(radiusOptions, id: \.self) { miles in
                menuItem("Within \(Int(miles)) miles", selected: model.radiusMiles == miles) {
                    Task { await model.setRadius(miles) }
                }
            }
        } label: {
            pill(distanceLabel, icon: "location.fill",
                 active: model.radiusMiles != nil && model.activePostcode != nil)
        }
    }

    private var distanceLabel: String {
        guard let miles = model.radiusMiles else { return "Any distance" }
        if let postcode = model.activePostcode { return "\(Int(miles)) mi · \(postcode)" }
        return model.locationDenied ? "Location off" : "Within \(Int(miles)) mi"
    }

    @ViewBuilder
    private func menuItem(_ title: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            if selected { Label(title, systemImage: "checkmark") } else { Text(title) }
        }
    }

    private func pill(_ title: String, icon: String, active: Bool, showsChevron: Bool = true) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
            Text(title).font(AppTypography.controlLabel).lineLimit(1)
            if showsChevron {
                Image(systemName: "chevron.down").font(.caption2)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .foregroundStyle(active ? Color.white : Color.primary)
        .glassEffect(
            active ? .regular.tint(.accentColor).interactive() : .regular.interactive(),
            in: .capsule
        )
    }
}

/// A modal calendar for choosing a single day to filter on.
private struct DatePickerSheet: View {
    let onPick: (Date) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var date: Date

    init(initialDate: Date, onPick: @escaping (Date) -> Void) {
        self.onPick = onPick
        _date = State(initialValue: initialDate)
    }

    var body: some View {
        NavigationStack {
            DatePicker("Event date", selection: $date, displayedComponents: .date)
                .datePickerStyle(.graphical)
                .padding()
                .frame(maxHeight: .infinity, alignment: .top)
                .navigationTitle("Pick a date")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Cancel") { dismiss() }
                    }
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Show") { onPick(date); dismiss() }
                    }
                }
        }
    }
}
