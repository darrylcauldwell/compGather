import Foundation
import SwiftData

/// A locally-stored favourite event. Persisted with SwiftData so favourites are
/// available offline. `competitionId` is unique so starring is idempotent.
@Model
final class Favourite {
    @Attribute(.unique) var competitionId: Int
    var name: String
    var dateStart: String
    var venueName: String
    var discipline: String?
    var url: String?
    var addedAt: Date

    init(
        competitionId: Int,
        name: String,
        dateStart: String,
        venueName: String,
        discipline: String?,
        url: String?,
        addedAt: Date = .now
    ) {
        self.competitionId = competitionId
        self.name = name
        self.dateStart = dateStart
        self.venueName = venueName
        self.discipline = discipline
        self.url = url
        self.addedAt = addedAt
    }

    convenience init(_ competition: Competition) {
        self.init(
            competitionId: competition.id,
            name: competition.name,
            dateStart: competition.dateStart,
            venueName: competition.venueName,
            discipline: competition.discipline,
            url: competition.url
        )
    }

    var startDate: Date? { DayDate.parse(dateStart) }
}
