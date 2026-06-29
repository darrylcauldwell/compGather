import SwiftUI

/// Horizontally-scrolling Liquid Glass discipline chips. Tapping toggles the
/// active discipline filter (nil == "All").
struct DisciplineChips: View {
    let disciplines: [String]
    let selected: String?
    let onSelect: (String?) -> Void

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            GlassEffectContainer(spacing: 8) {
                HStack(spacing: 8) {
                    chip(title: "All", isOn: selected == nil) { onSelect(nil) }
                    ForEach(disciplines, id: \.self) { discipline in
                        chip(title: discipline, isOn: selected == discipline) { onSelect(discipline) }
                    }
                }
                .padding(.horizontal)
            }
        }
    }

    @ViewBuilder
    private func chip(title: String, isOn: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(AppTypography.controlLabel)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
        }
        .buttonStyle(.plain)
        .foregroundStyle(isOn ? Color.white : Color.primary)
        .glassEffect(
            isOn ? .regular.tint(.accentColor).interactive() : .regular.interactive(),
            in: .capsule
        )
    }
}

/// Compact control showing the active "near me" postcode, or a button to enable it.
struct NearMeBar: View {
    let activePostcode: String?
    let onUseLocation: () -> Void
    let onClear: () -> Void

    var body: some View {
        HStack {
            if let postcode = activePostcode {
                Label("Near \(postcode)", systemImage: "location.fill")
                    .font(AppTypography.controlLabel)
                    .foregroundStyle(.secondary)
                Spacer()
                Button("Clear", action: onClear)
                    .font(AppTypography.controlLabel)
                    .buttonStyle(.glass)
            } else {
                Button(action: onUseLocation) {
                    Label("Events near me", systemImage: "location")
                        .font(AppTypography.controlLabel)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.glassProminent)
            }
        }
        .padding(.horizontal)
    }
}
