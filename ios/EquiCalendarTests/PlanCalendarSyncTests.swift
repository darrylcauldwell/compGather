import Foundation
import Testing
@testable import EquiCalendar

struct PlanCalendarSyncTests {
    @Test func markerParsesFromNotes() {
        let notes = "Dressage\nequicalendar-id:9001"
        #expect(PlanCalendarSync.competitionID(inNotes: notes) == 9001)
    }

    @Test func markerParsesWithoutDisciplineLine() {
        #expect(PlanCalendarSync.competitionID(inNotes: "equicalendar-id:42") == 42)
    }

    @Test func unmarkedNotesAreIgnored() {
        #expect(PlanCalendarSync.competitionID(inNotes: "A note the user wrote") == nil)
        #expect(PlanCalendarSync.competitionID(inNotes: nil) == nil)
        #expect(PlanCalendarSync.competitionID(inNotes: "equicalendar-id:not-a-number") == nil)
    }

    @Test func searchWindowStaysInsideEventKitFourYearCap() {
        let now = Date(timeIntervalSince1970: 1_780_000_000)
        let window = PlanCalendarSync.searchWindow(around: now)
        let span = window.end.timeIntervalSince(window.start)
        #expect(span > 0)
        #expect(span < 4 * 366 * 24 * 3600)
        #expect(window.start < now && now < window.end)
    }
}
