import CloudKit
import CoreData
import os
import SwiftUI
import UIKit

/// Saved events ("Plan"), stored with Core Data + CloudKit so they sync across
/// the user's devices and can be shared, read-write, with another person.
///
/// The list of events is the focus. Sharing mechanics live behind the toolbar
/// cog (`PlanSettingsView`) so the tab reads as a plan, not a share screen.
struct FavouritesView: View {
    @FetchRequest(sortDescriptors: [NSSortDescriptor(key: "dateStart", ascending: true)])
    private var favourites: FetchedResults<Favourite>

    @State private var showingSettings = false

    var body: some View {
        NavigationStack {
            content
                .navigationTitle("Plan")
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button {
                            showingSettings = true
                        } label: {
                            Label("Plan sharing", systemImage: "gearshape")
                        }
                    }
                }
                .sheet(isPresented: $showingSettings) {
                    PlanSettingsView()
                }
        }
    }

    @ViewBuilder
    private var content: some View {
        if favourites.isEmpty {
            ContentUnavailableView {
                Label("Nothing planned yet", systemImage: "checklist")
            } description: {
                Text("Tap the star on an event to add it to your plan — saved for offline access.")
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            List {
                ForEach(favourites, id: \.objectID) { favourite in
                    FavouriteCard(favourite: favourite)
                        .listRowSeparator(.hidden)
                        .listRowBackground(Color.clear)
                        .listRowInsets(.init(top: 6, leading: 16, bottom: 6, trailing: 16))
                }
                .onDelete(perform: delete)
            }
            .listStyle(.plain)
        }
    }

    private func delete(at offsets: IndexSet) {
        PlanStore.shared.delete(offsets.map { favourites[$0] })
    }
}

/// Plan sharing, presented from the Plan tab's toolbar cog. Two Liquid-Glass
/// cards — share your Plan, or join someone else's — kept off the main view.
private struct PlanSettingsView: View {
    @Environment(\.dismiss) private var dismiss

    @State private var shareContext: ShareContext?
    @State private var canShare = false
    @State private var isBusy = false
    @State private var message: String?

    private let log = Logger(subsystem: "dev.dreamfold.equicalendar", category: "Share")

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    shareCard
                    joinCard
                    if !canShare {
                        Text("Sign in to iCloud on this device to share your Plan.")
                            .font(AppTypography.cardMeta)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 4)
                    }
                }
                .padding(16)
            }
            .navigationTitle("Plan Sharing")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
            .task { canShare = await PlanStore.shared.iCloudAvailable() }
            .sheet(item: $shareContext) { context in
                CloudShareSheet(context: context)
            }
            .alert("Plan sharing", isPresented: .init(
                get: { message != nil },
                set: { if !$0 { message = nil } }
            )) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(message ?? "")
            }
        }
    }

    private var shareCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Share your Plan", systemImage: "person.2.fill")
                .font(AppTypography.cardTitle)
                .foregroundStyle(.primary)
            Text("Plan together — both of you can add and remove events, kept in sync across your iPhones.")
                .font(AppTypography.cardMeta)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Button {
                Task { await startShare() }
            } label: {
                Label("Share Plan", systemImage: "square.and.arrow.up")
                    .font(AppTypography.controlLabel)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.glassProminent)
            .disabled(isBusy || !canShare)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .glassEffect(.regular, in: .rect(cornerRadius: 20))
    }

    private var joinCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Join a shared Plan", systemImage: "person.badge.plus")
                .font(AppTypography.cardTitle)
                .foregroundStyle(.primary)
            Text("Got an invite? Copy the link the other person shared, then tap Join to add their Plan to yours.")
                .font(AppTypography.cardMeta)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Button {
                Task { await joinFromClipboard() }
            } label: {
                Label("Join from Link", systemImage: "link")
                    .font(AppTypography.controlLabel)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.glass)
            .disabled(isBusy)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .glassEffect(.regular, in: .rect(cornerRadius: 20))
    }

    private func startShare() async {
        isBusy = true
        defer { isBusy = false }
        do {
            let (share, container) = try await PlanStore.shared.makeShare()
            shareContext = ShareContext(share: share, container: container)
        } catch {
            log.error("Share prepare failed: \(error.localizedDescription, privacy: .public)")
            message = "Couldn't prepare the share: \(error.localizedDescription)"
        }
    }

    /// Accept a Plan invite by reading the share link from the clipboard — the
    /// reliable fallback for when the system share link won't open the app.
    private func joinFromClipboard() async {
        isBusy = true
        defer { isBusy = false }
        guard let clip = UIPasteboard.general.string, let url = shareURL(in: clip) else {
            message = "Copy the invite link first (other phone → Plan → cog → Share Plan → Copy Link), then tap \u{201C}Join from Link\u{201D}."
            return
        }
        do {
            try await PlanStore.shared.acceptShare(from: url)
            message = "Joining the shared plan — its events will appear here shortly."
        } catch {
            log.error("Join failed: \(error.localizedDescription, privacy: .public)")
            message = "Couldn't join: \(error.localizedDescription)"
        }
    }

    /// Pull an iCloud share URL out of clipboard text (which may be a whole message).
    private func shareURL(in text: String) -> URL? {
        let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.link.rawValue)
        let range = NSRange(text.startIndex..., in: text)
        for match in detector?.matches(in: text, range: range) ?? [] {
            if let url = match.url, url.absoluteString.contains("icloud.com/share") {
                return url
            }
        }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if let url = URL(string: trimmed), url.absoluteString.contains("icloud.com/share") {
            return url
        }
        return nil
    }
}

private struct FavouriteCard: View {
    @ObservedObject var favourite: Favourite

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(favourite.name ?? "")
                .font(AppTypography.cardTitle)
            Label(favourite.venueName ?? "", systemImage: "mappin.and.ellipse")
                .font(AppTypography.cardBody)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            HStack(spacing: 8) {
                TagBadge(
                    text: EventFormatting.dateText(start: favourite.startDate, end: nil),
                    systemImage: "calendar",
                    tint: .primary
                )
                if let discipline = favourite.discipline {
                    TagBadge(text: discipline, systemImage: "figure.equestrian.sports", tint: .accentColor)
                }
            }
            if let urlString = favourite.url, let url = URL(string: urlString) {
                Link(destination: url) {
                    Label("View on organiser site", systemImage: "safari")
                        .font(AppTypography.cardMeta)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .glassEffect(.regular, in: .rect(cornerRadius: 20))
    }
}
