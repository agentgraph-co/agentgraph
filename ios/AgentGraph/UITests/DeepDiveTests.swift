// DeepDiveTests — Navigate all screens and screenshot for visual verification

import XCTest

@MainActor
final class DeepDiveTests: XCTestCase {
    let screenshotDir = "/tmp/ios-deepdive"

    // MARK: - Helper

    func saveScreenshot(_ name: String) {
        let app = XCUIApplication()
        let screenshot = app.screenshot()
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)

        // Also save to disk for easy viewing
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
        return app
    }

    // MARK: - Tests

    func test01_LoginScreen() throws {
        let app = launchApp()
        saveScreenshot("01-login")

        XCTAssertTrue(app.staticTexts["AgentGraph"].exists)
        XCTAssertTrue(app.buttons["Sign In"].exists)
        XCTAssertTrue(app.buttons["Browse as Guest"].exists)
    }

    func test02_GuestMode_Feed() throws {
        let app = launchApp()

        let guestButton = app.buttons["Browse as Guest"]
        XCTAssertTrue(guestButton.waitForExistence(timeout: 5))
        guestButton.tap()
        sleep(2)
        saveScreenshot("02-feed-guest")

        XCTAssertTrue(app.tabBars.buttons["Feed"].exists)
        XCTAssertTrue(app.tabBars.buttons["Discover"].exists)
        XCTAssertTrue(app.tabBars.buttons["Graph"].exists)
        XCTAssertTrue(app.tabBars.buttons["Profile"].exists)
    }

    func test03_GuestMode_Discovery() throws {
        let app = launchApp()
        app.buttons["Browse as Guest"].tap()
        sleep(1)

        app.tabBars.buttons["Discover"].tap()
        sleep(1)
        saveScreenshot("03-discover")
    }

    func test04_GuestMode_Graph() throws {
        let app = launchApp()
        app.buttons["Browse as Guest"].tap()
        sleep(1)

        app.tabBars.buttons["Graph"].tap()
        sleep(2)
        saveScreenshot("04-graph")
    }

    func test05_GuestMode_Profile() throws {
        let app = launchApp()
        app.buttons["Browse as Guest"].tap()
        sleep(1)

        app.tabBars.buttons["Profile"].tap()
        sleep(1)
        saveScreenshot("05-profile-guest")

        XCTAssertTrue(app.staticTexts["Sign in to view your profile"].exists)
    }

    func test06_Login_And_Feed() throws {
        let app = launchApp()

        let emailField = app.textFields.firstMatch
        XCTAssertTrue(emailField.waitForExistence(timeout: 5))
        emailField.tap()
        emailField.typeText("kenne@agentgraph.io")

        let passwordField = app.secureTextFields.firstMatch
        passwordField.tap()
        passwordField.typeText("***REMOVED***")

        app.buttons["Sign In"].tap()
        sleep(3)
        saveScreenshot("06-feed-authenticated")

        XCTAssertTrue(app.tabBars.buttons["Feed"].exists)
    }

    func test07_Authenticated_Profile() throws {
        let app = launchApp()
        login(app: app)

        app.tabBars.buttons["Profile"].tap()
        sleep(2)
        saveScreenshot("07-profile-authenticated")
    }

    func test08_Settings() throws {
        let app = launchApp()
        login(app: app)

        app.tabBars.buttons["Profile"].tap()
        sleep(1)

        // Look for gear icon button
        let settingsButton = app.navigationBars.buttons["gearshape"]
        if settingsButton.waitForExistence(timeout: 3) {
            settingsButton.tap()
            sleep(1)
            saveScreenshot("08-settings")
        } else {
            saveScreenshot("08-settings-notfound")
        }
    }

    func test09_Discovery_Search() throws {
        let app = launchApp()
        login(app: app)

        app.tabBars.buttons["Discover"].tap()
        sleep(1)
        saveScreenshot("09-discover-authenticated")
    }

    func test10_Notifications() throws {
        let app = launchApp()
        login(app: app)

        app.tabBars.buttons["Feed"].tap()
        sleep(1)

        // Look for bell button
        let bellButton = app.navigationBars.buttons["bell"]
        if bellButton.waitForExistence(timeout: 3) {
            bellButton.tap()
            sleep(1)
            saveScreenshot("10-notifications")
        } else {
            saveScreenshot("10-notifications-nobell")
        }
    }

    func test11_DMs() throws {
        let app = launchApp()
        login(app: app)

        app.tabBars.buttons["Feed"].tap()
        sleep(1)

        let dmButton = app.navigationBars.buttons["envelope"]
        if dmButton.waitForExistence(timeout: 3) {
            dmButton.tap()
            sleep(1)
            saveScreenshot("11-dms")
        } else {
            saveScreenshot("11-dms-noenvelope")
        }
    }

    // MARK: - Login Helper

    func login(app: XCUIApplication) {
        guard app.buttons["Sign In"].waitForExistence(timeout: 3) else { return }

        let emailField = app.textFields.firstMatch
        guard emailField.waitForExistence(timeout: 3) else { return }
        emailField.tap()
        emailField.typeText("kenne@agentgraph.io")

        let passwordField = app.secureTextFields.firstMatch
        passwordField.tap()
        passwordField.typeText("***REMOVED***")

        app.buttons["Sign In"].tap()
        sleep(3)
    }
}
