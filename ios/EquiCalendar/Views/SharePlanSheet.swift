import os
import SwiftUI
import UIKit

/// Custom Liquid-Glass Plan-sharing sheet, presented from the Plan tab's cog.
/// Replaces the system `UICloudSharingController` — the share actions live inline
/// here rather than on a separate pushed page. Three states off
/// `PlanStore.shareRole`:
///   .notShared   → share hero + "join instead" fallback
///   .owner       → invite link + people list + Stop Sharing
///   .participant → whose-Plan context + people list + Leave
struct SharePlanSheet: View {
    @Environment(\.dismiss) private var dismiss

    @State private var canShare = false
    @State private var isBusy = false
    @State private var role: PlanStore.ShareRole = .notShared
    @State private var people: [PlanStore.PlanPerson] = []
    @State private var url: URL?
    @State private var ownerName: String?
    @State private var copied = false
    @State private var message: String?
    @State private var confirmStop = false
    @State private var confirmLeave = false
    @State private var personToRemove: PlanStore.PlanPerson?

    private let log = Logger(subsystem: "dev.dreamfold.equicalendar", category: "Share")

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    if !canShare {
                        noICloudCard
                    } else {
                        switch role {
                        case .notShared:   notSharedState
                        case .owner:       ownerState
                        case .participant: participantState
                        }
                    }
                }
                .padding(16)
            }
            .navigationTitle("Plan Sharing")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } }
            }
            .task {
                if Self.isSnapshot { loadSnapshotDemo(); return }
                canShare = await PlanStore.shared.iCloudAvailable()
                reload()
            }
            .alert("Plan sharing", isPresented: .init(
                get: { message != nil }, set: { if !$0 { message = nil } }
            )) {
                Button("OK", role: .cancel) {}
            } message: { Text(message ?? "") }
            .confirmationDialog(
                personToRemove.map { "Remove \($0.name)?" } ?? "Remove?",
                isPresented: .init(
                    get: { personToRemove != nil },
                    set: { if !$0 { personToRemove = nil } }
                ),
                titleVisibility: .visible
            ) {
                Button("Remove", role: .destructive) {
                    if let p = personToRemove { Task { await removePerson(p) } }
                }
                Button("Cancel", role: .cancel) { personToRemove = nil }
            } message: {
                Text("They'll lose access to this Plan. If they haven't accepted the invite yet, it's cancelled.")
            }
        }
    }

    // MARK: State (a) — not shared

    private var notSharedState: some View {
        VStack(spacing: 16) {
            card(centred: true) {
                Image(systemName: "figure.2.arms.open")
                    .font(AppTypography.heroSymbol).foregroundStyle(Color.accentColor)
                    .frame(maxWidth: .infinity)
                Text("Share your Plan")
                    .font(AppTypography.cardTitle)
                    .frame(maxWidth: .infinity)
                Text("Invite one other person to share this Plan. You'll both see the same events and can each add or remove them — kept in sync across your iPhones.")
                    .font(AppTypography.cardMeta).foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                Button { Task { await startShare() } } label: {
                    Group {
                        if isBusy { ProgressView() }
                        else { Label("Share Plan", systemImage: "square.and.arrow.up") }
                    }
                    .font(AppTypography.controlLabel)
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.glassProminent)
                .disabled(isBusy)
            }
            // Essential join path preserved (only in the not-shared state).
            card {
                Label("Join a shared Plan", systemImage: "person.badge.plus")
                    .font(AppTypography.cardTitle)
                Text("Got an invite? Copy the link the other person sent, then tap Join.")
                    .font(AppTypography.cardMeta).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Button { Task { await joinFromClipboard() } } label: {
                    Label("Join from Link", systemImage: "link")
                        .font(AppTypography.controlLabel).frame(maxWidth: .infinity)
                }
                .buttonStyle(.glass).disabled(isBusy)
            }
        }
    }

    // MARK: State (b) — owner, shared

    private var ownerState: some View {
        VStack(spacing: 16) {
            card {   // Invite link
                Label("Invite link", systemImage: "link").font(AppTypography.cardTitle)
                if let url {
                    Text(url.absoluteString)
                        .font(AppTypography.linkMono)
                        .lineLimit(1).truncationMode(.middle)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 12).padding(.vertical, 10)
                        .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                        .contentShape(Rectangle())
                        .onTapGesture { copyLink() }
                    HStack(spacing: 12) {
                        Button { copyLink() } label: {
                            Label(copied ? "Copied!" : "Copy Link",
                                  systemImage: copied ? "checkmark" : "doc.on.doc")
                                .font(AppTypography.controlLabel).frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.glass)
                        ShareLink(item: url) {
                            Label("Share…", systemImage: "square.and.arrow.up")
                                .font(AppTypography.controlLabel).frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.glassProminent)
                    }
                } else {
                    HStack(spacing: 8) {
                        ProgressView()
                        Text("Preparing link…")
                            .font(AppTypography.cardMeta).foregroundStyle(.secondary)
                    }
                }
                Text("Anyone with this link can view and edit your Plan.")
                    .font(AppTypography.cardMeta).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            peopleCard(allowRemove: true)
            card {   // Stop sharing
                Button(role: .destructive) { confirmStop = true } label: {
                    Label("Stop Sharing", systemImage: "person.2.slash")
                        .font(AppTypography.controlLabel).frame(maxWidth: .infinity)
                }
                .buttonStyle(.glass).tint(.red).disabled(isBusy)
            }
            .confirmationDialog("Stop sharing this Plan?",
                                isPresented: $confirmStop, titleVisibility: .visible) {
                Button("Stop Sharing", role: .destructive) { Task { await stopSharing() } }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("The other person will lose access and their copy stops updating. Your events stay on your Plan.")
            }
        }
    }

    // MARK: State (c) — participant

    private var participantState: some View {
        VStack(spacing: 16) {
            card(centred: true) {
                Image(systemName: "figure.2.arms.open")
                    .font(AppTypography.heroSymbol).foregroundStyle(Color.accentColor)
                    .frame(maxWidth: .infinity)
                Text(ownerName.map { "\($0)'s Plan" } ?? "Shared Plan")
                    .font(AppTypography.cardTitle).frame(maxWidth: .infinity)
                Text("You're sharing this Plan with \(ownerName ?? "someone"). You can both add and remove events — changes sync to both of you.")
                    .font(AppTypography.cardMeta).foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            peopleCard(allowRemove: false)
            card {   // Leave
                Button(role: .destructive) { confirmLeave = true } label: {
                    Label("Leave shared Plan",
                          systemImage: "rectangle.portrait.and.arrow.right")
                        .font(AppTypography.controlLabel).frame(maxWidth: .infinity)
                }
                .buttonStyle(.glass).tint(.red).disabled(isBusy)
            }
            .confirmationDialog("Leave this shared Plan?",
                                isPresented: $confirmLeave, titleVisibility: .visible) {
                Button("Leave", role: .destructive) { Task { await leave() } }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Its events will be removed from your Plan. You can re-join later with a new invite link.")
            }
        }
    }

    // MARK: People list (shared by states b & c)

    @ViewBuilder private func peopleCard(allowRemove: Bool) -> some View {
        if !people.isEmpty {
            card {
                Label("On this Plan", systemImage: "person.2").font(AppTypography.cardTitle)
                ForEach(Array(people.enumerated()), id: \.element.id) { index, person in
                    if index > 0 { Divider() }
                    personRow(person, allowRemove: allowRemove)
                }
            }
        }
    }

    private func personRow(_ p: PlanStore.PlanPerson, allowRemove: Bool) -> some View {
        HStack(spacing: 12) {
            ZStack {
                Circle().fill(Color.accentColor.opacity(0.15))
                let ini = initials(p.name)
                if ini.isEmpty {
                    Image(systemName: "person.crop.circle.fill").foregroundStyle(.secondary)
                } else {
                    Text(ini).font(AppTypography.badge).foregroundStyle(Color.accentColor)
                }
            }
            .frame(width: 36, height: 36)
            VStack(alignment: .leading, spacing: 2) {
                Text(p.isCurrentUser ? "\(p.name) (You)" : p.name).font(AppTypography.cardBody)
                if p.isOwner {
                    Text(p.isCurrentUser ? "You · Owner" : "Owner")
                        .font(AppTypography.cardMeta).foregroundStyle(.secondary)
                } else if p.status == .invited, let handle = p.handle {
                    Text(handle).font(AppTypography.cardMeta)
                        .foregroundStyle(.secondary).lineLimit(1)
                }
            }
            Spacer()
            statusBadge(p)
            if allowRemove, p.removeKey != nil {
                Button { personToRemove = p } label: {
                    Image(systemName: "minus.circle.fill")
                        .font(AppTypography.controlLabel)
                        .foregroundStyle(.red)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Remove \(p.name)")
            }
        }
    }

    @ViewBuilder private func statusBadge(_ p: PlanStore.PlanPerson) -> some View {
        switch p.status {
        case .owner:   EmptyView()
        case .joined:  TagBadge(text: "Joined", systemImage: "checkmark.circle.fill", tint: .green)
        case .invited: TagBadge(text: "Invited", systemImage: "hourglass", tint: .orange)
        }
    }

    // MARK: No-iCloud fallback

    private var noICloudCard: some View {
        card(centred: true) {
            Image(systemName: "icloud.slash")
                .font(AppTypography.heroSymbol).foregroundStyle(.secondary)
                .frame(maxWidth: .infinity)
            Text("iCloud needed to share").font(AppTypography.cardTitle)
                .frame(maxWidth: .infinity)
            Text("Sign in to iCloud on this iPhone to share your Plan.")
                .font(AppTypography.cardMeta).foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
    }

    // MARK: Card container (canonical glass trio)

    @ViewBuilder
    private func card<Content: View>(centred: Bool = false,
                                     @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: centred ? .center : .leading, spacing: 12) { content() }
            .frame(maxWidth: .infinity, alignment: centred ? .center : .leading)
            .padding(16)
            .glassEffect(.regular, in: .rect(cornerRadius: 20))
    }

    // MARK: Actions

    @MainActor private func reload() {
        let store = PlanStore.shared
        role = store.shareRole
        people = store.participants()
        url = store.shareURL
        ownerName = store.ownerName
    }

    /// Screenshot-only: render a representative "shared with family" owner state
    /// (fake link + names) so `fastlane snapshot` captures the sharing UI without a
    /// live iCloud account or real participant data. Never runs in production —
    /// FASTLANE_SNAPSHOT is only set by the screenshot UI test.
    static var isSnapshot: Bool { UserDefaults.standard.bool(forKey: "FASTLANE_SNAPSHOT") }

    private func loadSnapshotDemo() {
        canShare = true
        role = .owner
        url = URL(string: "https://www.icloud.com/share/0EquiCalendarFamilyPlan")
        people = [
            .init(name: "You", handle: nil, isOwner: true, isCurrentUser: true, status: .owner, removeKey: nil),
            .init(name: "Mum", handle: nil, isOwner: false, isCurrentUser: false, status: .joined, removeKey: "d1"),
            .init(name: "Daughter", handle: nil, isOwner: false, isCurrentUser: false, status: .invited, removeKey: "d2"),
        ]
    }

    private func startShare() async {
        isBusy = true; defer { isBusy = false }
        do { _ = try await PlanStore.shared.makeShare(); reload() }
        catch { present(error, "Couldn't prepare the share") }
    }

    private func stopSharing() async {
        isBusy = true; defer { isBusy = false }
        do {
            try await PlanStore.shared.stopSharing()
            role = .notShared            // optimistic — local mirror lags server
            url = nil; people = []
            reload()
        } catch { present(error, "Couldn't stop sharing") }
    }

    private func leave() async {
        isBusy = true; defer { isBusy = false }
        do { try await PlanStore.shared.leaveSharedPlan(); dismiss() }
        catch { present(error, "Couldn't leave") }
    }

    private func removePerson(_ p: PlanStore.PlanPerson) async {
        isBusy = true; defer { isBusy = false }
        do { try await PlanStore.shared.removeParticipant(p); reload() }
        catch { present(error, "Couldn't remove") }
        personToRemove = nil
    }

    private func joinFromClipboard() async {
        isBusy = true; defer { isBusy = false }
        guard let clip = UIPasteboard.general.string, let link = shareURL(in: clip) else {
            message = "Copy the invite link first, then tap \u{201C}Join from Link\u{201D}."
            return
        }
        do {
            try await PlanStore.shared.acceptShare(from: link)
            message = "Joining the shared Plan — its events will appear here shortly."
        } catch { present(error, "Couldn't join") }
    }

    private func copyLink() {
        guard let url else { return }
        UIPasteboard.general.url = url
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        copied = true
        Task { try? await Task.sleep(for: .seconds(1.5)); copied = false }
    }

    private func present(_ error: Error, _ prefix: String) {
        log.error("\(prefix, privacy: .public): \(error.localizedDescription, privacy: .public)")
        message = "\(prefix): \(error.localizedDescription)"
    }

    private func initials(_ name: String) -> String {
        name.split(separator: " ").prefix(2)
            .compactMap { $0.first }.map(String.init).joined().uppercased()
    }

    /// Pull an icloud.com/share URL from arbitrary clipboard text.
    private func shareURL(in text: String) -> URL? {
        let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.link.rawValue)
        let range = NSRange(text.startIndex..., in: text)
        for match in detector?.matches(in: text, range: range) ?? [] {
            if let u = match.url, u.absoluteString.contains("icloud.com/share") { return u }
        }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if let u = URL(string: trimmed), u.absoluteString.contains("icloud.com/share") { return u }
        return nil
    }
}
