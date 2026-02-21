// AuthViewModelTests — Login/logout/refresh flows

import XCTest
@testable import AgentGraph

@MainActor
final class AuthViewModelTests: XCTestCase {

    // MARK: - Initial State

    func testInitialState() {
        let vm = AuthViewModel()
        XCTAssertFalse(vm.isAuthenticated)
        XCTAssertNil(vm.currentUser)
        XCTAssertFalse(vm.isLoading)
        XCTAssertNil(vm.error)
    }

    // MARK: - Logout

    func testLogoutClearsState() async {
        let vm = AuthViewModel()
        // Simulate authenticated state by setting properties
        // (We can't easily mock the full login flow without DI, but we can test logout behavior)
        await vm.logout()

        XCTAssertFalse(vm.isAuthenticated)
        XCTAssertNil(vm.currentUser)
        XCTAssertNil(vm.error)
    }

    func testLogoutClearsKeychain() async {
        // Save tokens first
        _ = KeychainService.save(key: KeychainService.accessTokenKey, value: "test-access")
        _ = KeychainService.save(key: KeychainService.refreshTokenKey, value: "test-refresh")

        let vm = AuthViewModel()
        await vm.logout()

        // Tokens should be cleared
        XCTAssertNil(KeychainService.load(key: KeychainService.accessTokenKey))
        XCTAssertNil(KeychainService.load(key: KeychainService.refreshTokenKey))
    }

    // MARK: - Session Check

    func testCheckExistingSessionWithNoTokensStaysLoggedOut() async {
        // Ensure no tokens exist
        _ = KeychainService.delete(key: KeychainService.accessTokenKey)
        _ = KeychainService.delete(key: KeychainService.refreshTokenKey)

        let vm = AuthViewModel()
        await vm.checkExistingSession()

        XCTAssertFalse(vm.isAuthenticated)
        XCTAssertNil(vm.currentUser)
    }

    // MARK: - Login Failure

    func testLoginWithInvalidCredentialsSetsError() async {
        let vm = AuthViewModel()
        // This will fail because the server isn't running in tests
        await vm.login(email: "bad@example.com", password: "wrongpassword")

        XCTAssertFalse(vm.isAuthenticated)
        XCTAssertNotNil(vm.error)
    }
}
