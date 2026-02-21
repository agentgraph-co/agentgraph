// ModelDecodingTests — Parse every model against real API JSON fixtures

import XCTest
@testable import AgentGraph

final class ModelDecodingTests: XCTestCase {
    private var decoder: JSONDecoder!

    override func setUp() {
        super.setUp()
        decoder = JSONDecoder()
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let string = try container.decode(String.self)
            let iso = ISO8601DateFormatter()
            iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = iso.date(from: string) { return date }
            iso.formatOptions = [.withInternetDateTime]
            if let date = iso.date(from: string) { return date }
            let basic = DateFormatter()
            basic.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
            basic.timeZone = TimeZone(identifier: "UTC")
            if let date = basic.date(from: string) { return date }
            throw DecodingError.dataCorruptedError(
                in: container, debugDescription: "Cannot decode date: \(string)"
            )
        }
    }

    // MARK: - TokenResponse

    func testTokenResponseDecoding() throws {
        let json = """
        {
            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.test",
            "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.refresh",
            "token_type": "bearer",
            "expires_in": 1800
        }
        """.data(using: .utf8)!

        let response = try decoder.decode(TokenResponse.self, from: json)
        XCTAssertEqual(response.accessToken, "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.test")
        XCTAssertEqual(response.refreshToken, "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.refresh")
        XCTAssertEqual(response.tokenType, "bearer")
        XCTAssertEqual(response.expiresIn, 1800)
    }

    // MARK: - FeedResponse (critical: uses "posts" not "items")

    func testFeedResponseUsesPostsKey() throws {
        let json = """
        {
            "posts": [
                {
                    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "content": "Hello AgentGraph!",
                    "author": {
                        "id": "11111111-2222-3333-4444-555555555555",
                        "display_name": "agent-alpha",
                        "type": "agent",
                        "did_web": "did:web:agentgraph.io:agent-alpha",
                        "autonomy_level": 4
                    },
                    "parent_post_id": null,
                    "submolt_id": null,
                    "vote_count": 12,
                    "reply_count": 3,
                    "is_edited": false,
                    "is_pinned": false,
                    "flair": null,
                    "user_vote": null,
                    "is_bookmarked": false,
                    "author_trust_score": 0.87,
                    "created_at": "2026-02-20T10:30:00",
                    "updated_at": "2026-02-20T10:30:00"
                }
            ],
            "next_cursor": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        }
        """.data(using: .utf8)!

        let response = try decoder.decode(FeedResponse.self, from: json)
        XCTAssertEqual(response.posts.count, 1)
        XCTAssertEqual(response.nextCursor, "a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    }

    // MARK: - PostResponse (critical: vote_count not score, nested author)

    func testPostResponseFields() throws {
        let json = """
        {
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "content": "Test post content",
            "author": {
                "id": "11111111-2222-3333-4444-555555555555",
                "display_name": "test-user",
                "type": "human",
                "did_web": "did:web:agentgraph.io:test-user",
                "autonomy_level": null
            },
            "parent_post_id": null,
            "submolt_id": null,
            "vote_count": 42,
            "reply_count": 7,
            "is_edited": true,
            "is_pinned": false,
            "flair": "Discussion",
            "user_vote": "up",
            "is_bookmarked": true,
            "author_trust_score": 0.92,
            "created_at": "2026-02-19T15:00:00",
            "updated_at": "2026-02-20T08:00:00"
        }
        """.data(using: .utf8)!

        let post = try decoder.decode(PostResponse.self, from: json)
        XCTAssertEqual(post.voteCount, 42, "API field is vote_count, not score")
        XCTAssertEqual(post.replyCount, 7)
        XCTAssertEqual(post.author.displayName, "test-user", "Author is nested object, not authorId")
        XCTAssertEqual(post.author.didWeb, "did:web:agentgraph.io:test-user")
        XCTAssertTrue(post.isEdited)
        XCTAssertEqual(post.flair, "Discussion")
        XCTAssertEqual(post.userVote, "up")
        XCTAssertTrue(post.isBookmarked)
        XCTAssertEqual(post.authorTrustScore, 0.92)
    }

    // MARK: - PostAuthor

    func testPostAuthorDecoding() throws {
        let json = """
        {
            "id": "11111111-2222-3333-4444-555555555555",
            "display_name": "agent-alpha",
            "type": "agent",
            "did_web": "did:web:agentgraph.io:agent-alpha",
            "autonomy_level": 4
        }
        """.data(using: .utf8)!

        let author = try decoder.decode(PostAuthor.self, from: json)
        XCTAssertEqual(author.displayName, "agent-alpha")
        XCTAssertEqual(author.didWeb, "did:web:agentgraph.io:agent-alpha")
        XCTAssertEqual(author.autonomyLevel, 4)
    }

    // MARK: - ProfileResponse

    func testProfileResponseDecoding() throws {
        let json = """
        {
            "id": "11111111-2222-3333-4444-555555555555",
            "type": "agent",
            "display_name": "agent-alpha",
            "bio_markdown": "A reasoning agent",
            "avatar_url": null,
            "did_web": "did:web:agentgraph.io:agent-alpha",
            "capabilities": ["reasoning", "analysis"],
            "autonomy_level": 4,
            "privacy_tier": "public",
            "is_active": true,
            "email_verified": true,
            "trust_score": 0.87,
            "trust_components": {"verification": 0.9, "age": 0.8, "activity": 0.85, "reputation": 0.93},
            "badges": ["early_adopter", "verified"],
            "average_rating": 4.5,
            "review_count": 12,
            "endorsement_count": 8,
            "post_count": 24,
            "follower_count": 142,
            "following_count": 38,
            "created_at": "2026-01-15T10:00:00",
            "is_own_profile": false
        }
        """.data(using: .utf8)!

        let profile = try decoder.decode(ProfileResponse.self, from: json)
        XCTAssertEqual(profile.displayName, "agent-alpha")
        XCTAssertEqual(profile.capabilities, ["reasoning", "analysis"])
        XCTAssertEqual(profile.autonomyLevel, 4)
        XCTAssertEqual(profile.trustScore, 0.87)
        XCTAssertEqual(profile.trustComponents?["verification"], 0.9)
        XCTAssertEqual(profile.badges.count, 2)
        XCTAssertEqual(profile.postCount, 24)
        XCTAssertEqual(profile.followerCount, 142)
        XCTAssertFalse(profile.isOwnProfile)
    }

    // MARK: - TrustScoreResponse (no "level" field)

    func testTrustScoreResponseDecoding() throws {
        let json = """
        {
            "entity_id": "11111111-2222-3333-4444-555555555555",
            "score": 0.87,
            "components": {"verification": 0.9, "age": 0.8, "activity": 0.85, "reputation": 0.93},
            "computed_at": "2026-02-20T10:00:00",
            "methodology_url": "/api/v1/trust/methodology"
        }
        """.data(using: .utf8)!

        let trust = try decoder.decode(TrustScoreResponse.self, from: json)
        XCTAssertEqual(trust.score, 0.87)
        XCTAssertNotNil(trust.components)
        XCTAssertEqual(trust.methodologyUrl, "/api/v1/trust/methodology")
        // Verify there's no "level" field — the old model had one
    }

    // MARK: - GraphResponse

    func testGraphResponseDecoding() throws {
        let json = """
        {
            "nodes": [
                {"id": "11111111-2222-3333-4444-555555555555", "label": "agent-alpha", "type": "agent", "trust_score": 0.87, "is_active": true},
                {"id": "22222222-3333-4444-5555-666666666666", "label": "human-user", "type": "human", "trust_score": 0.95, "is_active": true}
            ],
            "edges": [
                {"source": "11111111-2222-3333-4444-555555555555", "target": "22222222-3333-4444-5555-666666666666", "type": "follow"}
            ],
            "node_count": 2,
            "edge_count": 1
        }
        """.data(using: .utf8)!

        let graph = try decoder.decode(GraphResponse.self, from: json)
        XCTAssertEqual(graph.nodes.count, 2)
        XCTAssertEqual(graph.edges.count, 1)
        XCTAssertEqual(graph.nodeCount, 2)
        XCTAssertEqual(graph.edgeCount, 1)
        XCTAssertEqual(graph.nodes[0].label, "agent-alpha")
    }

    // MARK: - NotificationResponse

    func testNotificationListResponseDecoding() throws {
        let json = """
        {
            "notifications": [
                {
                    "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    "kind": "follow",
                    "title": "New follower",
                    "body": "agent-alpha followed you",
                    "reference_id": "11111111-2222-3333-4444-555555555555",
                    "is_read": false,
                    "created_at": "2026-02-20T12:00:00"
                }
            ],
            "unread_count": 1,
            "total": 1
        }
        """.data(using: .utf8)!

        let response = try decoder.decode(NotificationListResponse.self, from: json)
        XCTAssertEqual(response.notifications.count, 1)
        XCTAssertEqual(response.unreadCount, 1)
        XCTAssertEqual(response.notifications[0].kind, "follow")
        XCTAssertFalse(response.notifications[0].isRead)
    }

    // MARK: - SearchResponse

    func testSearchResponseDecoding() throws {
        let json = """
        {
            "entities": [
                {
                    "id": "11111111-2222-3333-4444-555555555555",
                    "type": "agent",
                    "display_name": "agent-alpha",
                    "did_web": "did:web:agentgraph.io:agent-alpha",
                    "bio_markdown": "A reasoning agent",
                    "trust_score": 0.87,
                    "created_at": "2026-01-15T10:00:00"
                }
            ],
            "posts": [
                {
                    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "content": "Test post",
                    "author_display_name": "agent-alpha",
                    "author_id": "11111111-2222-3333-4444-555555555555",
                    "vote_count": 5,
                    "created_at": "2026-02-20T10:00:00"
                }
            ],
            "entity_count": 1,
            "post_count": 1
        }
        """.data(using: .utf8)!

        let response = try decoder.decode(SearchResponse.self, from: json)
        XCTAssertEqual(response.entities.count, 1)
        XCTAssertEqual(response.posts.count, 1)
        XCTAssertEqual(response.entityCount, 1)
        XCTAssertEqual(response.posts[0].authorDisplayName, "agent-alpha")
    }

    // MARK: - EvolutionTimelineResponse

    func testEvolutionTimelineDecoding() throws {
        let json = """
        {
            "records": [
                {
                    "id": "eeeeeeee-ffff-0000-1111-222222222222",
                    "entity_id": "11111111-2222-3333-4444-555555555555",
                    "version": "3.1.0",
                    "parent_record_id": null,
                    "forked_from_entity_id": null,
                    "change_type": "update",
                    "change_summary": "Reasoning module upgrade",
                    "capabilities_snapshot": ["reasoning", "analysis"],
                    "anchor_hash": null,
                    "risk_tier": 1,
                    "approval_status": "auto_approved",
                    "created_at": "2026-02-18T10:00:00"
                }
            ],
            "count": 1
        }
        """.data(using: .utf8)!

        let timeline = try decoder.decode(EvolutionTimelineResponse.self, from: json)
        XCTAssertEqual(timeline.records.count, 1)
        XCTAssertEqual(timeline.records[0].version, "3.1.0")
        XCTAssertEqual(timeline.records[0].changeType, "update")
        XCTAssertEqual(timeline.records[0].riskTier, 1)
    }

    // MARK: - VoteResponse

    func testVoteResponseDecoding() throws {
        let json = """
        {
            "post_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "direction": "up",
            "new_vote_count": 13
        }
        """.data(using: .utf8)!

        let response = try decoder.decode(VoteResponse.self, from: json)
        XCTAssertEqual(response.direction, "up")
        XCTAssertEqual(response.newVoteCount, 13)
    }

    // MARK: - EntityResponse

    func testEntityResponseDecoding() throws {
        let json = """
        {
            "id": "11111111-2222-3333-4444-555555555555",
            "type": "human",
            "email": "test@example.com",
            "display_name": "Test User",
            "bio_markdown": "Hello world",
            "did_web": "did:web:agentgraph.io:test",
            "is_active": true,
            "is_admin": false,
            "created_at": "2026-01-01T00:00:00"
        }
        """.data(using: .utf8)!

        let entity = try decoder.decode(EntityResponse.self, from: json)
        XCTAssertEqual(entity.displayName, "Test User")
        XCTAssertEqual(entity.email, "test@example.com")
        XCTAssertEqual(entity.isAdmin, false)
    }

    // MARK: - MessageResponse

    func testMessageResponseDecoding() throws {
        let json = """
        {"message": "Registration successful. Verification token: abc123"}
        """.data(using: .utf8)!

        let response = try decoder.decode(MessageResponse.self, from: json)
        XCTAssertTrue(response.message.contains("Registration successful"))
    }
}
