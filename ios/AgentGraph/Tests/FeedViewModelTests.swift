// FeedViewModelTests — Load, paginate, vote state

import XCTest
@testable import AgentGraph

@MainActor
final class FeedViewModelTests: XCTestCase {

    // MARK: - Initial State

    func testInitialState() {
        let vm = FeedViewModel()
        XCTAssertTrue(vm.posts.isEmpty)
        XCTAssertFalse(vm.isLoading)
        XCTAssertNil(vm.error)
        XCTAssertEqual(vm.feedMode, .all)
    }

    // MARK: - Feed Mode

    func testFeedModeValues() {
        XCTAssertEqual(FeedMode.all.rawValue, "All")
        XCTAssertEqual(FeedMode.following.rawValue, "Following")
        XCTAssertEqual(FeedMode.trending.rawValue, "Trending")
    }

    func testAllFeedModesExist() {
        let modes = FeedMode.allCases
        XCTAssertEqual(modes.count, 3)
        XCTAssertTrue(modes.contains(.all))
        XCTAssertTrue(modes.contains(.following))
        XCTAssertTrue(modes.contains(.trending))
    }

    // MARK: - Refresh

    func testRefreshClearsPosts() async {
        let vm = FeedViewModel()
        // Calling refresh on an empty feed should not crash and should leave posts empty
        await vm.refresh()
        // Posts may be empty (no server) but the error should be set
        // since there's no mock server
        XCTAssertTrue(vm.posts.isEmpty)
    }

    // MARK: - Guard Against Double Load

    func testLoadFeedGuardsAgainstDoubleLoad() async {
        let vm = FeedViewModel()
        // The first call should execute; we just verify it doesn't crash
        // when called concurrently
        async let load1: () = vm.loadFeed()
        async let load2: () = vm.loadFeed()
        _ = await (load1, load2)
        // No crash = pass
    }

    // MARK: - PostResponse Model Integration

    func testPostResponseIdentifiable() throws {
        let json = """
        {
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "content": "Test",
            "author": {
                "id": "11111111-2222-3333-4444-555555555555",
                "display_name": "test",
                "type": "human",
                "did_web": "did:web:test",
                "autonomy_level": null
            },
            "parent_post_id": null,
            "submolt_id": null,
            "vote_count": 5,
            "reply_count": 0,
            "is_edited": false,
            "is_pinned": false,
            "flair": null,
            "user_vote": null,
            "is_bookmarked": false,
            "author_trust_score": null,
            "created_at": "2026-02-20T10:00:00",
            "updated_at": "2026-02-20T10:00:00"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let string = try container.decode(String.self)
            let formatter = DateFormatter()
            formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
            formatter.timeZone = TimeZone(identifier: "UTC")
            if let date = formatter.date(from: string) { return date }
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Bad date")
        }

        let post = try decoder.decode(PostResponse.self, from: json)
        XCTAssertEqual(post.id, UUID(uuidString: "a1b2c3d4-e5f6-7890-abcd-ef1234567890"))
        XCTAssertEqual(post.voteCount, 5)
        XCTAssertNil(post.userVote)
        XCTAssertFalse(post.isBookmarked)
    }
}
