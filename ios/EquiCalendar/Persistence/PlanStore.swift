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
        guard let shared = priv.copy() as? NSPersistentStoreDescription else {
            fatalError("NSPersistentStoreDescription.copy() must return NSPersistentStoreDescription")
        }
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
        // initializeCloudKitSchema needs a real device signed into iCloud — it hard
        // TRAPS on the Simulator and during unit/UI-test runs (no CloudKit account),
        // which crashes the app on launch. Only attempt it on a device, outside tests.
        #if targetEnvironment(simulator)
        return
        #else
        guard ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] == nil else { return }
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
        #endif
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
        // Read-write to anyone with the link, so the other person can join from a
        // pasted link (not only a specific invited email). Persist it so the
        // permission is actually saved to CloudKit, not just set locally.
        share.publicPermission = .readWrite
        try await persistShare(share)
        return (share, ckContainer)
    }

    private func persistShare(_ share: CKShare) async throws {
        guard let privateStore else { return }
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            container.persistUpdatedShare(share, in: privateStore) { _, error in
                if let error { continuation.resume(throwing: error) } else { continuation.resume() }
            }
        }
    }

    /// Accept a share invitation (called from the scene delegate when the system
    /// link-tap routes here).
    func accept(_ metadata: CKShare.Metadata) {
        // One Plan at a time: don't accept a second share while already sharing
        // (owner) or already in someone else's Plan (participant).
        guard shareRole == .notShared else {
            log.info("Ignoring share invite — already in a sharing relationship")
            return
        }
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

    /// Accept a share from a pasted link — the reliable fallback when the system
    /// link-tap won't route to the app. Fetches the share metadata for the URL,
    /// then accepts it the same way.
    func acceptShare(from url: URL) async throws {
        guard shareRole == .notShared else { throw PlanError.alreadySharing }
        let metadata = try await fetchShareMetadata(for: url)
        accept(metadata)
    }

    private func fetchShareMetadata(for url: URL) async throws -> CKShare.Metadata {
        try await withCheckedThrowingContinuation { continuation in
            let operation = CKFetchShareMetadataOperation(shareURLs: [url])
            operation.shouldFetchRootRecord = false
            var fetched: CKShare.Metadata?
            operation.perShareMetadataResultBlock = { _, result in
                if case .success(let metadata) = result { fetched = metadata }
            }
            operation.fetchShareMetadataResultBlock = { result in
                switch result {
                case .success:
                    if let fetched { continuation.resume(returning: fetched) }
                    else { continuation.resume(throwing: PlanError.noShareAtURL) }
                case .failure(let error):
                    continuation.resume(throwing: error)
                }
            }
            CKContainer(identifier: Self.containerID).add(operation)
        }
    }

    enum PlanError: LocalizedError {
        case noPlan
        case noShareAtURL
        case alreadySharing

        var errorDescription: String? {
            switch self {
            case .noPlan: "Couldn't find your Plan."
            case .noShareAtURL: "That link isn't a valid Plan invite."
            case .alreadySharing:
                "You're already sharing a Plan. Stop sharing or leave it first to share with someone else."
            }
        }
    }

    // MARK: - Share management (custom sheet)

    /// Which sharing state the UI should render.
    enum ShareRole { case notShared, owner, participant }

    var shareRole: ShareRole {
        if sharedPlan != nil { return .participant }   // joined someone else's Plan
        return isShared ? .owner : .notShared
    }

    /// A person on the share, flattened for the view. No CloudKit types leak out.
    struct PlanPerson: Identifiable {
        let id = UUID()
        let name: String
        let handle: String?          // email/phone, shown for pending invitees with no name
        let isOwner: Bool
        let isCurrentUser: Bool
        let status: Status
        let removeKey: String?       // stable participant id; nil = not removable
        enum Status { case owner, joined, invited }
    }

    /// The CKShare on the user's OWN Plan (nil if never shared).
    private var ownedShare: CKShare? {
        guard let plan = privatePlan else { return nil }
        return try? container.fetchShares(matching: [plan.objectID])[plan.objectID]
    }

    /// The CKShare on a Plan shared *with* this user (participant side).
    private var acceptedShare: CKShare? {
        guard let plan = sharedPlan else { return nil }
        return try? container.fetchShares(matching: [plan.objectID])[plan.objectID]
    }

    /// Whichever share is relevant to the current role.
    private var currentShare: CKShare? { acceptedShare ?? ownedShare }

    /// Invite URL for the user's shared Plan. Nil until `makeShare()` has persisted
    /// the share to CloudKit (the server assigns the URL).
    var shareURL: URL? { ownedShare?.url }

    /// The given name of the person who shared their Plan with you (participant side).
    var ownerName: String? {
        guard let comps = acceptedShare?.owner.userIdentity.nameComponents else { return nil }
        let name = PersonNameComponentsFormatter().string(from: comps)
        return name.isEmpty ? nil : name
    }

    /// Read-only people list for the current share (owner first).
    func participants() -> [PlanPerson] {
        guard let share = currentShare else { return [] }
        let formatter = PersonNameComponentsFormatter()
        let meID = share.currentUserParticipant?.userIdentity.userRecordID
        return share.participants.compactMap { p -> PlanPerson? in
            guard p.acceptanceStatus != .removed else { return nil }
            let isOwner = p.role == .owner
            let handle = p.userIdentity.lookupInfo?.emailAddress
                ?? p.userIdentity.lookupInfo?.phoneNumber
            let name = p.userIdentity.nameComponents
                .map { formatter.string(from: $0) }
                .flatMap { $0.isEmpty ? nil : $0 }
            let status: PlanPerson.Status = isOwner
                ? .owner
                : (p.acceptanceStatus == .accepted ? .joined : .invited)
            let isCurrentUser = meID != nil && p.userIdentity.userRecordID == meID
            let pkey = p.userIdentity.userRecordID?.recordName ?? handle
            return PlanPerson(
                name: name ?? handle ?? (isOwner ? "Plan owner" : "Invited"),
                handle: name == nil ? nil : handle,
                isOwner: isOwner,
                isCurrentUser: isCurrentUser,
                status: status,
                removeKey: (isOwner || isCurrentUser) ? nil : pkey
            )
        }
        .sorted { $0.isOwner && !$1.isOwner }
    }

    /// OWNER: remove a participant — cancels a pending invite, or revokes access
    /// for someone who has joined. Matched by the stable key from `participants()`.
    func removeParticipant(_ person: PlanPerson) async throws {
        guard let key = person.removeKey, let share = ownedShare else { throw PlanError.noPlan }
        guard let participant = share.participants.first(where: { p in
            let pk = p.userIdentity.userRecordID?.recordName
                ?? p.userIdentity.lookupInfo?.emailAddress
                ?? p.userIdentity.lookupInfo?.phoneNumber
            return pk == key
        }) else { return }
        share.removeParticipant(participant)
        try await persistShare(share)
        log.info("Removed a participant from the Plan share")
    }

    /// OWNER: stop sharing. Deletes the CKShare on the server; the owner's events
    /// remain in the private store. The other person's copy stops syncing and is
    /// purged on their next sync.
    func stopSharing() async throws {
        guard let share = ownedShare else { throw PlanError.noPlan }
        let ckContainer = CKContainer(identifier: Self.containerID)
        _ = try await ckContainer.privateCloudDatabase.deleteRecord(withID: share.recordID)
        log.info("Stopped sharing Plan")
    }

    /// PARTICIPANT: leave a Plan shared with you. Purges the shared objects from
    /// the shared store (local mirror); the owner keeps everything.
    func leaveSharedPlan() async throws {
        guard let sharedStore, let share = acceptedShare else { throw PlanError.noPlan }
        let zoneID = share.recordID.zoneID
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            container.purgeObjectsAndRecordsInZone(with: zoneID, in: sharedStore) { _, error in
                if let error { cont.resume(throwing: error) } else { cont.resume() }
            }
        }
        log.info("Left shared Plan")
    }

    // MARK: -

    private func save() {
        guard viewContext.hasChanges else { return }
        do { try viewContext.save() } catch {
            log.error("Plan save failed: \(error.localizedDescription, privacy: .public)")
        }
    }
}
