// KeychainServiceTests — Save/load/delete roundtrips

import XCTest
@testable import AgentGraph

final class KeychainServiceTests: XCTestCase {
    private let testKey = "test_keychain_key"

    override func tearDown() {
        _ = KeychainService.delete(key: testKey)
        super.tearDown()
    }

    // MARK: - Save and Load

    func testSaveAndLoadRoundtrip() {
        let value = "test-token-value-\(UUID().uuidString)"
        let saved = KeychainService.save(key: testKey, value: value)
        XCTAssertTrue(saved)

        let loaded = KeychainService.load(key: testKey)
        XCTAssertEqual(loaded, value)
    }

    // MARK: - Overwrite

    func testSaveOverwritesExistingValue() {
        _ = KeychainService.save(key: testKey, value: "old-value")
        _ = KeychainService.save(key: testKey, value: "new-value")

        let loaded = KeychainService.load(key: testKey)
        XCTAssertEqual(loaded, "new-value")
    }

    // MARK: - Delete

    func testDeleteRemovesValue() {
        _ = KeychainService.save(key: testKey, value: "to-delete")
        let deleted = KeychainService.delete(key: testKey)
        XCTAssertTrue(deleted)

        let loaded = KeychainService.load(key: testKey)
        XCTAssertNil(loaded)
    }

    // MARK: - Nonexistent Key

    func testLoadNonexistentKeyReturnsNil() {
        let loaded = KeychainService.load(key: "nonexistent_key_\(UUID().uuidString)")
        XCTAssertNil(loaded)
    }

    // MARK: - Delete Nonexistent Key

    func testDeleteNonexistentKeySucceeds() {
        let deleted = KeychainService.delete(key: "nonexistent_key_\(UUID().uuidString)")
        XCTAssertTrue(deleted, "Deleting a nonexistent key should succeed (errSecItemNotFound)")
    }

    // MARK: - Token Keys

    func testAccessTokenKeyConstant() {
        XCTAssertEqual(KeychainService.accessTokenKey, "access_token")
    }

    func testRefreshTokenKeyConstant() {
        XCTAssertEqual(KeychainService.refreshTokenKey, "refresh_token")
    }
}
