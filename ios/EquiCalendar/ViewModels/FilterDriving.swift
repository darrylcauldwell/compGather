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

    // Venue pin — set by the Explore map hand-off or the venue search pill.
    var venueName: String? { get }
    func applyVenue(id: Int, name: String) async
    func clearVenue() async
    /// Whether the bar offers the venue-search pill (event lists yes; the
    /// Explore map has its own venue affordance — the pins).
    var showsVenueSearch: Bool { get }

    // Per-view pill visibility — which filter pills this view shows. Defaults
    // (see extension) keep the full set on Compete/Watch; Explore overrides them
    // to show only Mode + Distance.
    var showsSeries: Bool { get }
    var showsDiscipline: Bool { get }
    var showsDate: Bool { get }
    /// A dedicated Championships toggle (Watch only — Compete has it in Series).
    var showsChampionships: Bool { get }
    /// A "Hide Pony Club" toggle (Prepare only — filters out members-only PC events).
    var showsPonyClubFilter: Bool { get }
    var hidePonyClub: Bool { get }
    func setHidePonyClub(_ hide: Bool) async
}

extension FilterDriving {
    var showsVenueSearch: Bool { true }
    func applyVenue(id: Int, name: String) async {}
    var showsSeries: Bool { true }
    var showsDiscipline: Bool { true }
    var showsDate: Bool { true }
    var showsChampionships: Bool { false }
    var showsPonyClubFilter: Bool { false }
    var hidePonyClub: Bool { false }
    func setHidePonyClub(_ hide: Bool) async {}
}
