import CloudKit
import CoreData
import os

/// The Plan persistence stack: Core Data backed by CloudKit
/// (`NSPersistentCloudKitContainer`). Phase A wires the **private** store only —
/// the user's own Plan, synced across their own devices. Phase B adds the
/// **shared** store + `CKShare` so two people can co-maintain one Plan.
///
/// Replaces the old SwiftData store. Because CloudKit can't enforce uniqueness,
/// favourites are de-duplicated in code by `competitionId`.
@MainActor
final class PlanStore {
    static let shared = PlanStore()
    static let containerID = "iCloud.dev.dreamfold.equicalendar"

    let container: NSPersistentCloudKitContainer
    private let log = Logger(subsystem: "dev.dreamfold.equicalendar", category: "PlanStore")

    var viewContext: NSManagedObjectContext { container.viewContext }

    init() {
        container = NSPersistentCloudKitContainer(
            name: "EquiCalendar",
            managedObjectModel: PlanModel.make()
        )

        let store = container.persistentStoreDescriptions.first!
        store.url = NSPersistentContainer.defaultDirectoryURL().appendingPathComponent("private.sqlite")
        let options = NSPersistentCloudKitContainerOptions(containerIdentifier: Self.containerID)
        options.databaseScope = .private
        store.cloudKitContainerOptions = options
        // Required for CloudKit sync (and for the shared store added in Phase B).
        store.setOption(true as NSNumber, forKey: NSPersistentHistoryTrackingKey)
        store.setOption(true as NSNumber, forKey: NSPersistentStoreRemoteChangeNotificationPostOptionKey)

        container.loadPersistentStores { [log] _, error in
            if let error {
                // Degrade gracefully — the app must stay usable. A failed CloudKit
                // store still loads as a local store when there's no iCloud account.
                log.error("Plan store load failed: \(error.localizedDescription, privacy: .public)")
            }
        }
        container.viewContext.automaticallyMergesChangesFromParent = true
        container.viewContext.transactionAuthor = "app"
    }

    // MARK: - Plan

    /// The user's own Plan, created once. (Phase B will distinguish this private
    /// plan from a shared plan accepted from another user.)
    @discardableResult
    func ensureDefaultPlan() -> Plan {
        let request = NSFetchRequest<Plan>(entityName: "Plan")
        request.fetchLimit = 1
        if let existing = try? viewContext.fetch(request).first { return existing }
        let plan = Plan(context: viewContext)
        plan.uuid = UUID()
        plan.createdAt = .now
        plan.title = "My Plan"
        save()
        return plan
    }

    // MARK: - Favourites

    func isFavourite(_ competitionID: Int) -> Bool {
        let request = Favourite.fetchRequest()
        request.predicate = NSPredicate(format: "competitionId == %lld", Int64(competitionID))
        request.fetchLimit = 1
        return ((try? viewContext.count(for: request)) ?? 0) > 0
    }

    /// Add or remove the event from the Plan (dedup by competitionId).
    func toggle(_ competition: Competition) {
        let request = Favourite.fetchRequest()
        request.predicate = NSPredicate(format: "competitionId == %lld", Int64(competition.id))
        request.fetchLimit = 1
        if let existing = try? viewContext.fetch(request).first {
            viewContext.delete(existing)
        } else {
            let favourite = Favourite(context: viewContext)
            favourite.competitionId = Int64(competition.id)
            favourite.name = competition.name
            favourite.dateStart = competition.dateStart
            favourite.venueName = competition.venueName
            favourite.discipline = competition.discipline
            favourite.url = competition.url
            favourite.addedAt = .now
            favourite.plan = ensureDefaultPlan()
        }
        save()
    }

    func delete(_ favourites: [Favourite]) {
        favourites.forEach(viewContext.delete)
        save()
    }

    private func save() {
        guard viewContext.hasChanges else { return }
        do { try viewContext.save() } catch {
            log.error("Plan save failed: \(error.localizedDescription, privacy: .public)")
        }
    }
}
