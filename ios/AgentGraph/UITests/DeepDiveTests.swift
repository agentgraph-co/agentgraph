// DeepDiveTests — Navigate all screens and screenshot for visual verification
// Runs against STAGING (:8001) with seeded data

import XCTest

@MainActor
final class DeepDiveTests: XCTestCase {
    let screenshotDir = "/tmp/ios-deepdive"

    // MARK: - Helpers

    func saveScreenshot(_ name: String) {
        let app = XCUIApplication()
        let screenshot = app.screenshot()
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)

        let data = screenshot.pngRepresentation
        let url = URL(fileURLWithPath: "\(screenshotDir)/\(name).png")
        try? FileManager.default.createDirectory(
            at: URL(fileURLWithPath: screenshotDir),
            withIntermediateDirectories: true
        )
        try? data.write(to: url)
    }

    func launchApp() -> XCUIApplication {
        let app = XCUIApplication()
        app.launch()

        // Handle system alerts (Save Password, notifications, etc.)
        addUIInterruptionMonitor(withDescription: "System Dialog") { alert in
            let notNow = alert.buttons["Not Now"]
            if notNow.exists {
                notNow.tap()
                return true
            }
            let dismiss = alert.buttons["Dismiss"]
            if dismiss.exists {
                dismiss.tap()
                return true
            }
            let ok = alert.buttons["OK"]
            if ok.exists {
                ok.tap()
                return true
            }
            let allow = alert.buttons["Allow"]
            if allow.exists {
                allow.tap()
                return true
            }
            let dontAllow = alert.buttons["Don\u{2019}t Allow"]
            if dontAllow.exists {
                dontAllow.tap()
                return true
            }
            return false
        }

        return app
    }

    /// Tap "Staging" in the environment segmented picker on login screen.
    /// Force-toggles through Development first to ensure onChange fires.
    func selectStaging(app: XCUIApplication) {
        let stagingButton = app.buttons["Staging"]
        guard stagingButton.waitForExistence(timeout: 3) else { return }

        // If Staging is already selected, tap Development first to force onChange
        let devButton = app.buttons["Development"]
        if devButton.exists {
            devButton.tap()
            sleep(1)
        }
        stagingButton.tap()
        sleep(1) // Wait for health check + API environment update
    }

    /// Switch to staging and log in with admin credentials
    func login(app: XCUIApplication) {
        guard app.buttons["Sign In"].waitForExistence(timeout: 5) else { return }

        selectStaging(app: app)

        let emailField = app.textFields.firstMatch
        guard emailField.waitForExistence(timeout: 3) else { return }
        emailField.tap()
        let testEmail = ProcessInfo.processInfo.environment["ADMIN_EMAIL"] ?? "***REMOVED***"
        emailField.typeText(testEmail)

        let passwordField = app.secureTextFields.firstMatch
        passwordField.tap()
        let testPassword = ProcessInfo.processInfo.environment["ADMIN_PASSWORD"] ?? ""
        XCTAssertFalse(testPassword.isEmpty, "Set ADMIN_PASSWORD env var for UI tests")
        passwordField.typeText(testPassword)

        app.buttons["Sign In"].tap()
        sleep(2)

        // Tap the app to trigger system dialog dismissal
        app.tap()
        sleep(2)
    }

    // MARK: - Core Screen Tests

    func test01_LoginScreen() throws {
        let app = launchApp()

        let signIn = app.buttons["Sign In"]
        XCTAssertTrue(signIn.waitForExistence(timeout: 10), "Login screen should load")
        saveScreenshot("01-login-initial")

        XCTAssertTrue(app.staticTexts["AgentGraph"].exists)
        XCTAssertTrue(app.buttons["Browse as Guest"].exists)

        selectStaging(app: app)
        saveScreenshot("01-login-staging-selected")
    }

    func test02_GuestMode_Feed_Staging() throws {
        let app = launchApp()
        selectStaging(app: app)

        let guestButton = app.buttons["Browse as Guest"]
        XCTAssertTrue(guestButton.waitForExistence(timeout: 5))
        guestButton.tap()
        sleep(3)
        saveScreenshot("02-feed-guest-staging")

        XCTAssertTrue(app.tabBars.buttons["Feed"].exists)
        XCTAssertTrue(app.tabBars.buttons["Discover"].exists)
        XCTAssertTrue(app.tabBars.buttons["Graph"].exists)
        XCTAssertTrue(app.tabBars.buttons["Profile"].exists)
    }

    func test03_GuestMode_Discovery_Staging() throws {
        let app = launchApp()
        selectStaging(app: app)
        app.buttons["Browse as Guest"].tap()
        sleep(1)

        app.tabBars.buttons["Discover"].tap()
        sleep(1)
        saveScreenshot("03-discover-guest-staging")
    }

    func test04_GuestMode_Graph_Staging() throws {
        let app = launchApp()
        selectStaging(app: app)
        app.buttons["Browse as Guest"].tap()
        sleep(1)

        app.tabBars.buttons["Graph"].tap()
        sleep(2)
        saveScreenshot("04-graph-guest-staging")
    }

    func test05_GuestMode_Profile() throws {
        let app = launchApp()
        selectStaging(app: app)
        app.buttons["Browse as Guest"].tap()
        sleep(1)

        app.tabBars.buttons["Profile"].tap()
        sleep(1)
        saveScreenshot("05-profile-guest")

        XCTAssertTrue(app.staticTexts["Sign in to view your profile"].exists)
    }

    // MARK: - Authenticated Tests with Staging Data

    func test06_Login_Staging() throws {
        let app = launchApp()
        login(app: app)
        saveScreenshot("06-feed-authenticated-staging")

        XCTAssertTrue(app.tabBars.buttons["Feed"].exists)
    }

    func test07_Feed_Has_Seeded_Posts() throws {
        let app = launchApp()
        login(app: app)

        // Wait for feed to load after dismissing any system dialogs
        sleep(3)

        // Tap the app to trigger interruption handler for Save Password dialog
        app.tap()
        sleep(2)

        saveScreenshot("07-feed-seeded-posts")
    }

    func test08_Authenticated_Profile() throws {
        let app = launchApp()
        login(app: app)

        app.tabBars.buttons["Profile"].tap()
        sleep(2)
        saveScreenshot("08-profile-authenticated-staging")

        XCTAssertFalse(app.staticTexts["Sign in to view your profile"].exists)
    }

    func test09_Settings() throws {
        let app = launchApp()
        login(app: app)

        app.tabBars.buttons["Profile"].tap()
        sleep(1)

        let settingsButton = app.navigationBars.buttons["gearshape"]
        if settingsButton.waitForExistence(timeout: 3) {
            settingsButton.tap()
            sleep(1)
            saveScreenshot("09-settings-staging")
        } else {
            saveScreenshot("09-settings-notfound")
        }
    }

    func test10_Discovery_Search_Seeded_Entity() throws {
        let app = launchApp()
        login(app: app)

        app.tabBars.buttons["Discover"].tap()
        sleep(1)

        let searchField = app.searchFields.firstMatch
        if searchField.waitForExistence(timeout: 3) {
            searchField.tap()
            searchField.typeText("Sarah")
            sleep(2)
            saveScreenshot("10-discover-search-sarah")
        } else {
            saveScreenshot("10-discover-no-searchfield")
        }
    }

    func test11_Discovery_Search_Agent() throws {
        let app = launchApp()
        login(app: app)

        app.tabBars.buttons["Discover"].tap()
        sleep(1)

        let searchField = app.searchFields.firstMatch
        if searchField.waitForExistence(timeout: 3) {
            searchField.tap()
            searchField.typeText("CodeReview")
            sleep(2)
            saveScreenshot("11-discover-search-agent")
        } else {
            saveScreenshot("11-discover-no-searchfield")
        }
    }

    func test12_Graph_With_Nodes() throws {
        let app = launchApp()
        login(app: app)

        app.tabBars.buttons["Graph"].tap()
        sleep(3)
        saveScreenshot("12-graph-authenticated-staging")
    }

    func test13_Notifications() throws {
        let app = launchApp()
        login(app: app)

        app.tabBars.buttons["Feed"].tap()
        sleep(1)

        let bellButton = app.navigationBars.buttons["bell"]
        if bellButton.waitForExistence(timeout: 3) {
            bellButton.tap()
            sleep(2)
            saveScreenshot("13-notifications-staging")
        } else {
            saveScreenshot("13-notifications-nobell")
        }
    }

    func test14_DMs() throws {
        let app = launchApp()
        login(app: app)

        app.tabBars.buttons["Feed"].tap()
        sleep(1)

        let dmButton = app.navigationBars.buttons["envelope"]
        if dmButton.waitForExistence(timeout: 3) {
            dmButton.tap()
            sleep(1)
            saveScreenshot("14-dms-staging")
        } else {
            saveScreenshot("14-dms-noenvelope")
        }
    }

    func test15_Bookmarks() throws {
        let app = launchApp()
        login(app: app)

        app.tabBars.buttons["Profile"].tap()
        sleep(1)

        let bookmarks = app.buttons["Bookmarks"]
        if bookmarks.waitForExistence(timeout: 3) {
            bookmarks.tap()
            sleep(1)
            saveScreenshot("15-bookmarks-staging")
        } else {
            app.swipeUp()
            sleep(1)
            if bookmarks.waitForExistence(timeout: 2) {
                bookmarks.tap()
                sleep(1)
                saveScreenshot("15-bookmarks-staging")
            } else {
                saveScreenshot("15-bookmarks-notfound")
            }
        }
    }

    func test16_Communities() throws {
        let app = launchApp()
        login(app: app)

        app.tabBars.buttons["Profile"].tap()
        sleep(1)

        let communities = app.buttons["Communities"]
        if communities.waitForExistence(timeout: 3) {
            communities.tap()
            sleep(2)
            saveScreenshot("16-communities-staging")
        } else {
            app.swipeUp()
            sleep(1)
            if communities.waitForExistence(timeout: 2) {
                communities.tap()
                sleep(2)
                saveScreenshot("16-communities-staging")
            } else {
                saveScreenshot("16-communities-notfound")
            }
        }
    }

    func test17_Marketplace() throws {
        let app = launchApp()
        login(app: app)

        app.tabBars.buttons["Profile"].tap()
        sleep(1)

        let marketplace = app.buttons["Marketplace"]
        if marketplace.waitForExistence(timeout: 3) {
            marketplace.tap()
            sleep(2)
            saveScreenshot("17-marketplace-staging")
        } else {
            app.swipeUp()
            sleep(1)
            if marketplace.waitForExistence(timeout: 2) {
                marketplace.tap()
                sleep(2)
                saveScreenshot("17-marketplace-staging")
            } else {
                saveScreenshot("17-marketplace-notfound")
            }
        }
    }

    func test18_Leaderboard() throws {
        let app = launchApp()
        login(app: app)

        app.tabBars.buttons["Profile"].tap()
        sleep(1)

        let leaderboard = app.buttons["Leaderboard"]
        if leaderboard.waitForExistence(timeout: 3) {
            leaderboard.tap()
            sleep(2)
            saveScreenshot("18-leaderboard-staging")
        } else {
            app.swipeUp()
            sleep(1)
            if leaderboard.waitForExistence(timeout: 2) {
                leaderboard.tap()
                sleep(2)
                saveScreenshot("18-leaderboard-staging")
            } else {
                saveScreenshot("18-leaderboard-notfound")
            }
        }
    }

    func test19_Activity_Timeline() throws {
        let app = launchApp()
        login(app: app)

        app.tabBars.buttons["Profile"].tap()
        sleep(1)

        let activity = app.buttons["Activity"]
        if activity.waitForExistence(timeout: 3) {
            activity.tap()
            sleep(2)
            saveScreenshot("19-activity-staging")
        } else {
            app.swipeUp()
            sleep(1)
            if activity.waitForExistence(timeout: 2) {
                activity.tap()
                sleep(2)
                saveScreenshot("19-activity-staging")
            } else {
                saveScreenshot("19-activity-notfound")
            }
        }
    }

    func test20_Feed_Scroll_And_Interact() throws {
        let app = launchApp()
        login(app: app)

        // Dismiss any system dialogs by tapping
        app.tap()
        sleep(1)

        // Scroll down to load more posts
        app.swipeUp()
        sleep(1)
        app.swipeUp()
        sleep(1)
        saveScreenshot("20-feed-scrolled-staging")

        // Scroll back to top
        app.swipeDown()
        app.swipeDown()
        sleep(1)
        saveScreenshot("20-feed-top-staging")
    }
}
