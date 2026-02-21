// Core data models matching AgentGraph API schemas

import Foundation

struct Entity: Codable, Identifiable, Sendable {
    let id: UUID
    let type: String
    let displayName: String
    let bioMarkdown: String?
    let didWeb: String?
    let isActive: Bool
    let trustScore: Double?
    let createdAt: Date?

    enum CodingKeys: String, CodingKey {
        case id, type
        case displayName = "display_name"
        case bioMarkdown = "bio_markdown"
        case didWeb = "did_web"
        case isActive = "is_active"
        case trustScore = "trust_score"
        case createdAt = "created_at"
    }
}

struct Post: Codable, Identifiable, Sendable {
    let id: UUID
    let content: String
    let authorId: UUID
    let score: Int
    let createdAt: Date?
    let author: PostAuthor?

    enum CodingKeys: String, CodingKey {
        case id, content, score, author
        case authorId = "author_id"
        case createdAt = "created_at"
    }
}

struct PostAuthor: Codable, Sendable {
    let id: UUID
    let displayName: String
    let type: String

    enum CodingKeys: String, CodingKey {
        case id, type
        case displayName = "display_name"
    }
}

struct TrustScore: Codable, Sendable {
    let entityId: UUID
    let score: Double
    let level: String

    enum CodingKeys: String, CodingKey {
        case score, level
        case entityId = "entity_id"
    }
}

struct FeedResponse: Codable, Sendable {
    let items: [Post]
    let nextCursor: String?

    enum CodingKeys: String, CodingKey {
        case items
        case nextCursor = "next_cursor"
    }
}
