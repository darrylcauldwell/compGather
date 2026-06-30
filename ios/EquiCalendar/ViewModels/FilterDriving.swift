import Foundation
import Observation

/// The filter surface shared by Compete/Watch (an events list) and Explore (a
/// venue map). `FilterBar` is generic over this so the exact same pills —
/// discipline, date, distance, series — drive every tab. The tier pill
/// (Level/Type) is gated on `showsTier`, and the venue pill on `venueName`,
/// so a tab can opt out of the parts that don't apply to it.
@MainActor
protocol FilterDriving: AnyObject, Observable {
    // Series / pathway (NSEA, Trailblazers, BS classes…)
    var series: String? { get }
    func setSeries(_ token: String?) async

    // Tier — "Level" on Compete, "Type" on Watch; hidden where `showsTier` is false.
    var showsTier: Bool { get }
    var isWatch: Bool { get }
    var tier: String? { get }
    func setTier(_ token: String?) async

    // Discipline
    var discipline: String? { get }
    var availableDisciplines: [String] { get }
    func setDiscipline(_ discipline: String?) async

    // Date scope / specific day
    var dateScope: DateScope { get }
    var customDate: Date? { get }
    var dateFilterActive: Bool { get }
    func setDateScope(_ scope: DateScope) async
    func setCustomDate(_ date: Date) async

    // Distance radius + resolved location state
    var radiusMiles: Double? { get }
    var activePostcode: String? { get }
    var locationDenied: Bool { get }
    func setRadius(_ miles: Double?) async
    func retryLocation() async

    // Venue hand-off (only the Compete list sets one; map/Watch report nil)
    var venueName: String? { get }
    func clearVenue() async
}
