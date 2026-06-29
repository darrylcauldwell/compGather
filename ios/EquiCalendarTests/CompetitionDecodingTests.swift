import Foundation
import Testing

@testable import EquiCalendar

struct CompetitionDecodingTests {
    @Test func decodesApiPayload() throws {
        let json = """
        [{
          "id": 42, "source_id": 3, "name": "Spring Dressage Championships",
          "date_start": "2026-05-15", "date_end": "2026-05-17",
          "venue_name": "Test Arena", "venue_postcode": "TE1 2ST",
          "discipline": "Dressage", "latitude": 51.5, "longitude": -0.1,
          "distance_miles": 12.4, "event_type": "competition",
          "tags": ["discipline:dressage", "type:competition", "level:championship"],
          "url": "https://example.com/e/42",
          "first_seen_at": "2026-01-01T00:00:00", "last_seen_at": "2026-01-02T00:00:00"
        }]
        """.data(using: .utf8)!

        let comps = try JSONDecoder().decode([Competition].self, from: json)
        let comp = try #require(comps.first)
        #expect(comp.id == 42)
        #expect(comp.name == "Spring Dressage Championships")
        #expect(comp.discipline == "Dressage")
        #expect(comp.distanceMiles == 12.4)
        #expect(comp.tags.contains("level:championship"))
        #expect(comp.disciplineTags == ["discipline:dressage"])
        #expect(comp.startDate != nil)
    }

    @Test func optionalFieldsTolerateNulls() throws {
        let json = """
        {
          "id": 1, "source_id": 1, "name": "Minimal",
          "date_start": "2026-06-01", "date_end": null,
          "venue_name": "V", "venue_postcode": null, "discipline": null,
          "latitude": null, "longitude": null, "distance_miles": null,
          "event_type": "show", "tags": [], "url": null,
          "first_seen_at": "2026-01-01T00:00:00", "last_seen_at": "2026-01-01T00:00:00"
        }
        """.data(using: .utf8)!

        let comp = try JSONDecoder().decode(Competition.self, from: json)
        #expect(comp.dateEnd == nil)
        #expect(comp.discipline == nil)
        #expect(comp.tags.isEmpty)
        #expect(comp.eventType == "show")
    }

    @Test func filterBuildsQueryItems() {
        var filter = EventFilter()
        filter.discipline = "Dressage"
        filter.eventType = "show"
        filter.postcode = "SW1A 1AA"
        let names = Set(filter.queryItems.map(\.name))
        #expect(names == ["discipline", "event_type", "postcode"])
    }
}
