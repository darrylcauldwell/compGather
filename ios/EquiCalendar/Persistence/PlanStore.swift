import CloudKit
import CoreData
import os

/// The Plan persistence stack: Core Data backed by CloudKit
/// (`NSPersistentCloudKitContainer`), with a **private** store (the user's own
/// Plan, synced across their devices) and a **shared** store (a Plan shared with
/// them by someone else). Sharing the private Plan via `CKShare` lets two people
/// co-maintain one list.
///
/// CloudKit can't enforce uniqueness, so favourites are de-duplicated in code by
/// `competitionId`.
@MainActor
final class PlanStore {
    static let shared = PlanStore()
    static let containerID = "iCloud.dev.dreamfold.equicalendar"

    let container: NSPersistentCloudKitContainer
    private(set) var privateStore: NSPersistentStore?
    private(set) var sharedStore: NSPersistentStore?
    private let log = Logger(subsystem: "dev.dreamfold.equicalendar", category: "PlanStore")

    var viewContext: NSManagedObjectContext { container.viewContext }

    init() {
        container = NSPersistentCloudKitContainer(
            name: "EquiCalendar",
            managedObjectModel: PlanModel.make()
        )
        let base = NSPersistentContainer.defaultDirectoryURL()

        // Private store — the user's own Plan.
        let priv = container.persistentStoreDescriptions.first!
        priv.url = base.appendingPathComponent("private.sqlite")
        priv.cloudKitContainerOptions = Self.options(scope: .private)
        priv.setOption(true as NSNumber, forKey: NSPersistentHistoryTrackingKey)
        priv.setOption(true as NSNumber, forKey: NSPersistentStoreRemoteChangeNotificationPostOptionKey)

        // Shared store — Plans others have shared with this user (CKShare accept).
        let shared = priv.copy() as! NSPersistentStoreDescription
        shared.url = base.appendingPathComponent("shared.sqlite")
        shared.cloudKitContainerOptions = Self.options(scope: .shared)
        container.persistentStoreDescriptions.append(shared)

        container.loadPersistentStores { [weak self] description, error in
            guard let self else { return }
            if let error {
                // Degrade gracefully — a CloudKit store still loads locally with
                // no iCloud account; the app must stay usable.
                self.log.error("Plan store load failed: \(error.localizedDescription, privacy: .public)")
                return
            }
            guard let url = description.url,
                  let store = self.container.persistentStoreCoordinator.persistentStore(for: url) else { return }
            if description.cloudKitContainerOptions?.databaseScope == .shared {
                self.sharedStore = store
            } else {
                self.privateStore = store
            }
        }
        container.viewContext.automaticallyMergesChangesFromParent = true
        container.viewContext.transactionAuthor = "app"

        #if DEBUG
        initializeSchemaForDevelopmentIfNeeded()
        #endif
    }

    #if DEBUG
    /// One-time (per install): push the full CloudKit schema to the DEVELOPMENT
    /// environment by running a debug build. Then promote it to Production in the
    /// CloudKit Dashboard so TestFlight/App Store builds can sync/share.
    private func initializeSchemaForDevelopmentIfNeeded() {
        let key = "ck_dev_schema_initialized_v1"
        guard !UserDefaults.standard.bool(forKey: key) else { return }
        do {
            try container.initializeCloudKitSchema(options: [])
            UserDefaults.standard.set(true, forKey: key)
            log.info("CloudKit development schema initialized")
        } catch {
            // Most likely not signed into iCloud — retried on the next launch.
            log.error("initializeCloudKitSchema failed: \(error.localizedDescription, privacy: .public)")
        }
    }
    #endif

    private static func options(scope: CKDatabase.Scope) -> NSPersistentCloudKitContainerOptions {
        let options = NSPersistentCloudKitContainerOptions(containerIdentifier: containerID)
        options.databaseScope = scope
        return options
    }

    // MARK: - Plans

    private func plans(in store: NSPersistentStore?) -> [Plan] {
        guard let store else { return [] }
        let request = NSFetchRequest<Plan>(entityName: "Plan")
        request.affectedStores = [store]
        return (try? viewContext.fetch(request)) ?? []
    }

    var privatePlan: Plan? { plans(in: privateStore).first }
    /// A Plan accepted from someone else (lives in the shared store).
    var sharedPlan: Plan? { plans(in: sharedStore).first }
    /// The plan new favourites are added to: the shared one if collaborating, else own.
    var activePlan: Plan? { sharedPlan ?? privatePlan }

    /// The user's own Plan (created once, in the private store).
    @discardableResult
    func ensurePrivatePlan() -> Plan? {
        if let existing = privatePlan { return existing }
        guard let privateStore else { return nil }
        let plan = Plan(context: viewContext)
        plan.uuid = UUID()
        plan.createdAt = .now
        plan.title = "My Plan"
        viewContext.assign(plan, to: privateStore)   // required with multiple stores
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

    /// Add or remove the event (dedup by competitionId across both stores).
    func toggle(_ competition: Competition) {
        let request = Favourite.fetchRequest()
        request.predicate = NSPredicate(format: "competitionId == %lld", Int64(competition.id))
        request.fetchLimit = 1
        if let existing = try? viewContext.fetch(request).first {
            viewContext.delete(existing)
        } else if let plan = activePlan ?? ensurePrivatePlan() {
            let favourite = Favourite(context: viewContext)
            favourite.competitionId = Int64(competition.id)
            favourite.name = competition.name
            favourite.dateStart = competition.dateStart
            favourite.venueName = competition.venueName
            favourite.discipline = competition.discipline
            favourite.url = competition.url
            favourite.addedAt = .now
            favourite.plan = plan
            // New objects must be assigned to a store when several are configured —
            // put it in the same store as the plan it belongs to.
            if let store = plan.objectID.persistentStore {
                viewContext.assign(favourite, to: store)
            }
        }
        save()
    }

    func delete(_ favourites: [Favourite]) {
        favourites.forEach(viewContext.delete)
        save()
    }

    // MARK: - Sharing

    /// Whether the device can share (signed into iCloud).
    func iCloudAvailable() async -> Bool {
        let status = try? await CKContainer(identifier: Self.containerID).accountStatus()
        return status == .available
    }

    /// True once the user's Plan has been shared with someone.
    var isShared: Bool {
        guard let plan = privatePlan else { return false }
        let shares = try? container.fetchShares(matching: [plan.objectID])
        return (shares?[plan.objectID]) != nil
    }

    /// Create (or fetch the existing) CKShare for the user's Plan, to present in
    /// the share sheet. Read-write so both people can add/remove.
    func makeShare() async throws -> (CKShare, CKContainer) {
        guard let plan = ensurePrivatePlan() else { throw PlanError.noPlan }
        if let existing = try container.fetchShares(matching: [plan.objectID])[plan.objectID] {
            return (existing, CKContainer(identifier: Self.containerID))
        }
        let (_, share, ckContainer) = try await container.share([plan], to: nil)
        share[CKShare.SystemFieldKey.title] = "EquiCalendar Plan" as CKRecordValue
        share.publicPermission = .readWrite
        return (share, ckContainer)
    }

    /// Accept a share invitation (called from the scene delegate).
    func accept(_ metadata: CKShare.Metadata) {
        guard let sharedStore else {
            log.error("Cannot accept share: shared store not loaded")
            return
        }
        container.acceptShareInvitations(from: [metadata], into: sharedStore) { [log] _, error in
            if let error {
                log.error("Accept share failed: \(error.localizedDescription, privacy: .public)")
            }
        }
    }

    enum PlanError: Error { case noPlan }

    // MARK: -

    private func save() {
        guard viewContext.hasChanges else { return }
        do { try viewContext.save() } catch {
            log.error("Plan save failed: \(error.localizedDescription, privacy: .public)")
        }
    }
}
