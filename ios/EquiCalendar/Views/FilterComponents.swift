import SwiftUI

/// Discoverable filter bar: labelled Liquid Glass pills that open menus for
/// discipline, date scope, location, and distance radius. Each pill shows the
/// current selection so the active filters are always visible.
struct FilterBar: View {
    let model: EventsViewModel

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            GlassEffectContainer(spacing: 8) {
                HStack(spacing: 8) {
                    disciplineMenu
                    dateMenu
                    locationControl
                    if model.activePostcode != nil { radiusMenu }
                }
                .padding(.horizontal)
            }
        }
    }

    private var disciplineMenu: some View {
        Menu {
            menuItem("All disciplines", selected: model.filter.discipline == nil) {
                Task { await model.setDiscipline(nil) }
            }
            ForEach(model.availableDisciplines, id: \.self) { discipline in
                menuItem(discipline, selected: model.filter.discipline == discipline) {
                    Task { await model.setDiscipline(discipline) }
                }
            }
        } label: {
            pill(model.filter.discipline ?? "All disciplines",
                 icon: "figure.equestrian.sports",
                 active: model.filter.discipline != nil)
        }
    }

    private var dateMenu: some View {
        Menu {
            ForEach(DateScope.allCases) { scope in
                menuItem(scope.title, selected: model.dateScope == scope) {
                    Task { await model.setDateScope(scope) }
                }
            }
        } label: {
            pill(model.dateScope.title, icon: "calendar", active: model.dateScope != .upcoming)
        }
    }

    @ViewBuilder
    private var locationControl: some View {
        if let postcode = model.activePostcode {
            Menu {
                Button("Clear location", systemImage: "xmark", role: .destructive) {
                    Task { await model.clearLocation() }
                }
            } label: {
                pill("Near \(postcode)", icon: "location.fill", active: true)
            }
        } else {
            Button {
                Task { await model.useMyLocation() }
            } label: {
                pill("Near me", icon: "location", active: false, showsChevron: false)
            }
            .buttonStyle(.plain)
        }
    }

    private var radiusMenu: some View {
        Menu {
            menuItem("Any distance", selected: model.radiusMiles == nil) {
                Task { await model.setRadius(nil) }
            }
            ForEach(radiusOptions, id: \.self) { miles in
                menuItem("\(Int(miles)) miles", selected: model.radiusMiles == miles) {
                    Task { await model.setRadius(miles) }
                }
            }
        } label: {
            pill(model.radiusMiles.map { "\(Int($0)) mi" } ?? "Any distance",
                 icon: "ruler", active: model.radiusMiles != nil)
        }
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
