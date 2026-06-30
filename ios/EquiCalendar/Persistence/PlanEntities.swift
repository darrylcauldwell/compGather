import CoreData

/// The Plan is the shareable root: one per user (their own), plus any shared
/// plan accepted from someone else (added in the sharing phase). Favourites are
/// its children, so sharing the Plan shares the whole list.
@objc(Plan)
final class Plan: NSManagedObject {
    @NSManaged var uuid: UUID?
    @NSManaged var createdAt: Date?
    @NSManaged var title: String?
    @NSManaged var favourites: NSSet?
}

/// A saved event in a Plan. CloudKit-backed, so: no unique constraint
/// (dedup is done in code by `competitionId`) and all attributes optional.
@objc(Favourite)
final class Favourite: NSManagedObject {
    @NSManaged var competitionId: Int64
    @NSManaged var name: String?
    @NSManaged var dateStart: String?
    @NSManaged var venueName: String?
    @NSManaged var discipline: String?
    @NSManaged var url: String?
    @NSManaged var addedAt: Date?
    @NSManaged var plan: Plan?

    var startDate: Date? { dateStart.flatMap(DayDate.parse) }

    static func fetchRequest() -> NSFetchRequest<Favourite> {
        NSFetchRequest<Favourite>(entityName: "Favourite")
    }
}

/// Programmatic Core Data model (no .xcdatamodeld bundle to hand-craft). Built
/// to be CloudKit-compatible: optional attributes, relationships with inverses,
/// no unique constraints.
enum PlanModel {
    static func make() -> NSManagedObjectModel {
        let model = NSManagedObjectModel()

        let plan = NSEntityDescription()
        plan.name = "Plan"
        plan.managedObjectClassName = NSStringFromClass(Plan.self)

        let fav = NSEntityDescription()
        fav.name = "Favourite"
        fav.managedObjectClassName = NSStringFromClass(Favourite.self)

        func attr(_ name: String, _ type: NSAttributeType, def: Any? = nil) -> NSAttributeDescription {
            let a = NSAttributeDescription()
            a.name = name
            a.attributeType = type
            a.isOptional = true            // CloudKit requires optional or default
            if let def { a.defaultValue = def }
            return a
        }

        let planProps = [
            attr("uuid", .UUIDAttributeType),
            attr("createdAt", .dateAttributeType),
            attr("title", .stringAttributeType),
        ]
        let favProps = [
            attr("competitionId", .integer64AttributeType, def: 0),
            attr("name", .stringAttributeType),
            attr("dateStart", .stringAttributeType),
            attr("venueName", .stringAttributeType),
            attr("discipline", .stringAttributeType),
            attr("url", .stringAttributeType),
            attr("addedAt", .dateAttributeType),
        ]

        let favourites = NSRelationshipDescription()
        favourites.name = "favourites"
        favourites.destinationEntity = fav
        favourites.minCount = 0
        favourites.maxCount = 0                // 0 == to-many
        favourites.deleteRule = .cascadeDeleteRule
        favourites.isOptional = true

        let planRel = NSRelationshipDescription()
        planRel.name = "plan"
        planRel.destinationEntity = plan
        planRel.minCount = 0
        planRel.maxCount = 1
        planRel.deleteRule = .nullifyDeleteRule
        planRel.isOptional = true

        favourites.inverseRelationship = planRel
        planRel.inverseRelationship = favourites

        plan.properties = planProps + [favourites]
        fav.properties = favProps + [planRel]
        model.entities = [plan, fav]
        return model
    }
}
