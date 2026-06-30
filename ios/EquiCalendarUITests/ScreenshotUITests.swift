import XCTest

/// App Store screenshot capture via `fastlane snapshot`.
///
/// Walks the four main tabs (Compete / Watch / Explore / Plan), opens an event
/// detail, and snapshots each. The app reads from the live API, so each step
/// waits for real content (a list cell or a map) to appear before capturing.
/// Waits are generous and failures are non-fatal — a slow network should never
/// abort the whole run; we capture whatever rendered.
final class ScreenshotUITests: XCTestCase {
    override func setUp() {
        super.setUp()
        continueAfterFailure = true
    }

    @MainActor
    func testCaptureAppStoreScreenshots() throws {
        let app = XCUIApplication()
        setupSnapshot(app)
        app.launch()

        let tabBar = app.tabBars.firstMatch
        _ = tabBar.waitForExistence(timeout: 30)

        // 01 — Compete (default tab): wait for the events list to populate.
        tapTab(app, "Compete")
        waitForContent(app)
        snapshot("01Compete")

        // 02 — Watch (spectator events).
        tapTab(app, "Watch")
        waitForContent(app)
        snapshot("02Watch")

        // 03 — Explore (venue map). The map view takes a beat to render tiles.
        tapTab(app, "Explore")
        _ = app.maps.firstMatch.waitForExistence(timeout: 30)
        sleep(4)
        snapshot("03Explore")

        // 04 — Event detail: back to Compete, open the first event.
        tapTab(app, "Compete")
        waitForContent(app)
        let firstCell = app.cells.firstMatch
        if firstCell.waitForExistence(timeout: 20) {
            firstCell.tap()
            // Detail shows an "Add to Calendar" button once loaded.
            _ = app.buttons["Add to Calendar"].waitForExistence(timeout: 20)
            sleep(2)
            snapshot("04Detail")
            // Return to the list for the next capture.
            app.navigationBars.buttons.firstMatch.tap()
        }

        // 05 — Plan (saved favourites / empty state).
        tapTab(app, "Plan")
        sleep(2)
        snapshot("05Plan")
    }

    // MARK: - Helpers

    @MainActor
    private func tapTab(_ app: XCUIApplication, _ label: String) {
        let button = app.tabBars.buttons[label]
        if button.waitForExistence(timeout: 15) {
            button.tap()
        }
    }

    /// Wait for a list cell to appear (content loaded) or time out gracefully.
    @MainActor
    private func waitForContent(_ app: XCUIApplication) {
        let cell = app.cells.firstMatch
        if !cell.waitForExistence(timeout: 25) {
            // No cells (slow network or empty state) — still give the UI a moment.
            sleep(3)
        } else {
            // Let the glass filter bar and rows settle before capturing.
            sleep(2)
        }
    }
}
