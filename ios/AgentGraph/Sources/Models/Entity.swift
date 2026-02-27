// API data models matching AgentGraph backend schemas
// All types are Codable + Sendable for Swift 6 strict concurrency

import Foundation

// MARK: - Auth

struct LoginRequest: Codable, Sendable {
    let email: String
    let password: String
}

struct RegisterRequest: Codable, Sendable {
    let email: String
    let password: String
    let displayName: String

    enum CodingKeys: String, CodingKey {
        case email, password
        case displayName = "display_name"
    }
}

struct TokenResponse: Codable, Sendable {
    let accessToken: String
    let refreshToken: String
    let tokenType: String
    let expiresIn: Int

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
        case tokenType = "token_type"
        case expiresIn = "expires_in"
    }
}

struct RefreshRequest: Codable, Sendable {
    let refreshToken: String

    enum CodingKeys: String, CodingKey {
        case refreshToken = "refresh_token"
    }
}

struct MessageResponse: Codable, Sendable {
    let message: String
}

// MARK: - Bookmark

struct BookmarkResponse: Codable, Sendable {
    let bookmarked: Bool
    let message: String
}

// MARK: - Entity

struct EntityResponse: Codable, Identifiable, Sendable {
    let id: UUID
    let type: String
    let email: String?
    let displayName: String
    let bioMarkdown: String
    let didWeb: String
    let isActive: Bool
    let isAdmin: Bool?
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, type, email
        case displayName = "display_name"
        case bioMarkdown = "bio_markdown"
        case didWeb = "did_web"
        case isActive = "is_active"
        case isAdmin = "is_admin"
        case createdAt = "created_at"
    }
}

// MARK: - Feed

struct PostAuthor: Codable, Sendable {
    let id: UUID
    let displayName: String
    let type: String
    let didWeb: String
    let autonomyLevel: Int?
    let avatarUrl: String?

    enum CodingKeys: String, CodingKey {
        case id, type
        case displayName = "display_name"
        case didWeb = "did_web"
        case autonomyLevel = "autonomy_level"
        case avatarUrl = "avatar_url"
    }
}

struct PostResponse: Codable, Identifiable, Sendable {
    let id: UUID
    let content: String
    let author: PostAuthor
    let parentPostId: UUID?
    let submoltId: UUID?
    let voteCount: Int
    let replyCount: Int
    let isEdited: Bool
    let isPinned: Bool
    let flair: String?
    let userVote: String?
    let isBookmarked: Bool
    let authorTrustScore: Double?
    let createdAt: Date
    let updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id, content, author, flair
        case parentPostId = "parent_post_id"
        case submoltId = "submolt_id"
        case voteCount = "vote_count"
        case replyCount = "reply_count"
        case isEdited = "is_edited"
        case isPinned = "is_pinned"
        case userVote = "user_vote"
        case isBookmarked = "is_bookmarked"
        case authorTrustScore = "author_trust_score"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct FeedResponse: Codable, Sendable {
    let posts: [PostResponse]
    let nextCursor: String?

    enum CodingKeys: String, CodingKey {
        case posts
        case nextCursor = "next_cursor"
    }
}

struct CreatePostRequest: Codable, Sendable {
    let content: String
    let parentPostId: UUID?
    let submoltId: UUID?
    let flair: String?

    enum CodingKeys: String, CodingKey {
        case content, flair
        case parentPostId = "parent_post_id"
        case submoltId = "submolt_id"
    }
}

struct VoteRequest: Codable, Sendable {
    let direction: String
}

struct VoteResponse: Codable, Sendable {
    let postId: UUID
    let direction: String
    let newVoteCount: Int

    enum CodingKeys: String, CodingKey {
        case direction
        case postId = "post_id"
        case newVoteCount = "new_vote_count"
    }
}

// MARK: - Profile

struct ProfileResponse: Codable, Identifiable, Sendable {
    let id: UUID
    let type: String
    let displayName: String
    let bioMarkdown: String
    let avatarUrl: String?
    let didWeb: String
    let capabilities: [String]?
    let autonomyLevel: Int?
    let privacyTier: String
    let isActive: Bool
    let emailVerified: Bool
    let trustScore: Double?
    let trustComponents: [String: Double]?
    let badges: [String]
    let averageRating: Double?
    let reviewCount: Int
    let endorsementCount: Int
    let postCount: Int
    let followerCount: Int
    let followingCount: Int
    let createdAt: Date
    let isOwnProfile: Bool

    enum CodingKeys: String, CodingKey {
        case id, type, badges
        case displayName = "display_name"
        case bioMarkdown = "bio_markdown"
        case avatarUrl = "avatar_url"
        case didWeb = "did_web"
        case capabilities
        case autonomyLevel = "autonomy_level"
        case privacyTier = "privacy_tier"
        case isActive = "is_active"
        case emailVerified = "email_verified"
        case trustScore = "trust_score"
        case trustComponents = "trust_components"
        case averageRating = "average_rating"
        case reviewCount = "review_count"
        case endorsementCount = "endorsement_count"
        case postCount = "post_count"
        case followerCount = "follower_count"
        case followingCount = "following_count"
        case createdAt = "created_at"
        case isOwnProfile = "is_own_profile"
    }
}

struct UpdateProfileRequest: Codable, Sendable {
    var displayName: String?
    var bioMarkdown: String?
    var avatarUrl: String?
    var privacyTier: String?

    enum CodingKeys: String, CodingKey {
        case displayName = "display_name"
        case bioMarkdown = "bio_markdown"
        case avatarUrl = "avatar_url"
        case privacyTier = "privacy_tier"
    }
}

// MARK: - Social

struct EntitySummary: Codable, Identifiable, Sendable {
    let id: UUID
    let type: String
    let displayName: String
    let didWeb: String
    let avatarUrl: String?

    enum CodingKeys: String, CodingKey {
        case id, type
        case displayName = "display_name"
        case didWeb = "did_web"
        case avatarUrl = "avatar_url"
    }
}

struct FollowListResponse: Codable, Sendable {
    let entities: [EntitySummary]
    let count: Int
    let total: Int
}

struct SocialStatsResponse: Codable, Sendable {
    let entityId: String
    let followingCount: Int
    let followersCount: Int

    enum CodingKeys: String, CodingKey {
        case entityId = "entity_id"
        case followingCount = "following_count"
        case followersCount = "followers_count"
    }
}

// MARK: - Trust

struct TrustComponentDetail: Codable, Sendable {
    let raw: Double
    let weight: Double
    let contribution: Double
}

struct TrustScoreResponse: Codable, Sendable {
    let entityId: UUID
    let score: Double
    let components: [String: Double]?
    let componentDetails: [String: TrustComponentDetail]?
    let computedAt: Date
    let methodologyUrl: String

    enum CodingKeys: String, CodingKey {
        case score, components
        case entityId = "entity_id"
        case componentDetails = "component_details"
        case computedAt = "computed_at"
        case methodologyUrl = "methodology_url"
    }
}

struct AttestationResponse: Codable, Identifiable, Sendable {
    let id: UUID
    let attesterId: UUID
    let attesterDisplayName: String
    let targetEntityId: UUID
    let attestationType: String
    let context: String?
    let weight: Double
    let comment: String?
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, context, weight, comment
        case attesterId = "attester_id"
        case attesterDisplayName = "attester_display_name"
        case targetEntityId = "target_entity_id"
        case attestationType = "attestation_type"
        case createdAt = "created_at"
    }
}

struct AttestationListResponse: Codable, Sendable {
    let attestations: [AttestationResponse]
    let count: Int?
    let total: Int?

    var itemCount: Int { count ?? total ?? attestations.count }
}

struct CreateAttestationRequest: Codable, Sendable {
    let attestationType: String
    let context: String?
    let comment: String?

    enum CodingKeys: String, CodingKey {
        case context, comment
        case attestationType = "attestation_type"
    }
}

struct ContestTrustRequest: Codable, Sendable {
    let reason: String
}

struct ContestTrustResponse: Codable, Sendable {
    let message: String
    let flagId: UUID

    enum CodingKeys: String, CodingKey {
        case message
        case flagId = "flag_id"
    }
}

struct ContextualTrustResponse: Codable, Sendable {
    let entityId: UUID
    let context: String
    let score: Double?
    let attestationCount: Int

    enum CodingKeys: String, CodingKey {
        case context, score
        case entityId = "entity_id"
        case attestationCount = "attestation_count"
    }
}

// MARK: - Graph (#3: Use String IDs to match backend)

struct APIGraphNode: Codable, Identifiable, Sendable {
    let id: String
    let label: String
    let type: String
    let trustScore: Double?
    let isActive: Bool
    let clusterId: Int?
    let avatarUrl: String?

    enum CodingKeys: String, CodingKey {
        case id, label, type
        case trustScore = "trust_score"
        case isActive = "is_active"
        case clusterId = "cluster_id"
        case avatarUrl = "avatar_url"
    }
}

struct APIGraphEdge: Codable, Sendable {
    let source: String
    let target: String
    let type: String
    let weight: Double?
    let attestationType: String?

    enum CodingKeys: String, CodingKey {
        case source, target, type, weight
        case attestationType = "attestation_type"
    }
}

struct GraphResponse: Codable, Sendable {
    let nodes: [APIGraphNode]
    let edges: [APIGraphEdge]
    let nodeCount: Int
    let edgeCount: Int

    enum CodingKeys: String, CodingKey {
        case nodes, edges
        case nodeCount = "node_count"
        case edgeCount = "edge_count"
    }
}

// MARK: - Graph Clusters

struct ClusterInfo: Codable, Identifiable, Sendable {
    let clusterId: Int
    let size: Int
    let avgTrust: Double
    let memberCount: Int
    let dominantType: String

    var id: Int { clusterId }

    enum CodingKeys: String, CodingKey {
        case size
        case clusterId = "cluster_id"
        case avgTrust = "avg_trust"
        case memberCount = "member_count"
        case dominantType = "dominant_type"
    }
}

struct ClustersResponse: Codable, Sendable {
    let clusters: [ClusterInfo]
    let totalClusters: Int

    enum CodingKeys: String, CodingKey {
        case clusters
        case totalClusters = "total_clusters"
    }
}

// MARK: - Trust Flow

struct TrustFlowAttestation: Codable, Sendable {
    let attesterId: String
    let attesterName: String
    let attestationType: String
    let weight: Double
    let children: [TrustFlowAttestation]

    enum CodingKeys: String, CodingKey {
        case children, weight
        case attesterId = "attester_id"
        case attesterName = "attester_name"
        case attestationType = "attestation_type"
    }
}

struct TrustFlowResponse: Codable, Sendable {
    let entityId: String
    let trustScore: Double?
    let attestations: [TrustFlowAttestation]

    enum CodingKeys: String, CodingKey {
        case attestations
        case entityId = "entity_id"
        case trustScore = "trust_score"
    }
}

struct NetworkStatsEntry: Codable, Identifiable, Sendable {
    let id: String
    let displayName: String
    let type: String
    let followerCount: Int?
    let connectionCount: Int?

    enum CodingKeys: String, CodingKey {
        case id, type
        case displayName = "display_name"
        case followerCount = "follower_count"
        case connectionCount = "connection_count"
    }
}

struct NetworkStatsResponse: Codable, Sendable {
    let totalEntities: Int
    let totalHumans: Int
    let totalAgents: Int
    let totalFollows: Int
    let avgFollowers: Double
    let avgFollowing: Double
    let mostFollowed: [NetworkStatsEntry]
    let mostConnected: [NetworkStatsEntry]

    enum CodingKeys: String, CodingKey {
        case mostFollowed = "most_followed"
        case mostConnected = "most_connected"
        case totalEntities = "total_entities"
        case totalHumans = "total_humans"
        case totalAgents = "total_agents"
        case totalFollows = "total_follows"
        case avgFollowers = "avg_followers"
        case avgFollowing = "avg_following"
    }
}

// MARK: - Notifications

struct NotificationResponse: Codable, Identifiable, Sendable {
    let id: UUID
    let kind: String
    let title: String
    let body: String
    let referenceId: String?
    let isRead: Bool
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, kind, title, body
        case referenceId = "reference_id"
        case isRead = "is_read"
        case createdAt = "created_at"
    }
}

struct NotificationListResponse: Codable, Sendable {
    let notifications: [NotificationResponse]
    let unreadCount: Int
    let total: Int

    enum CodingKeys: String, CodingKey {
        case notifications, total
        case unreadCount = "unread_count"
    }
}

// MARK: - Search

struct SearchEntityResult: Codable, Identifiable, Sendable {
    let id: UUID
    let type: String
    let displayName: String
    let didWeb: String
    let bioMarkdown: String
    let avatarUrl: String?
    let trustScore: Double?
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, type
        case displayName = "display_name"
        case didWeb = "did_web"
        case bioMarkdown = "bio_markdown"
        case avatarUrl = "avatar_url"
        case trustScore = "trust_score"
        case createdAt = "created_at"
    }
}

struct SearchPostResult: Codable, Identifiable, Sendable {
    let id: UUID
    let content: String
    let authorDisplayName: String
    let authorId: UUID
    let voteCount: Int
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, content
        case authorDisplayName = "author_display_name"
        case authorId = "author_id"
        case voteCount = "vote_count"
        case createdAt = "created_at"
    }
}

struct SearchResponse: Codable, Sendable {
    let entities: [SearchEntityResult]
    let posts: [SearchPostResult]
    let entityCount: Int
    let postCount: Int

    enum CodingKeys: String, CodingKey {
        case entities, posts
        case entityCount = "entity_count"
        case postCount = "post_count"
    }
}

// MARK: - Privacy

struct PrivacyTierResponse: Codable, Sendable {
    let tier: String
    let options: [String]
}

struct UpdatePrivacyRequest: Codable, Sendable {
    let tier: String
}

struct PrivacyUpdateResponse: Codable, Sendable {
    let message: String
    let tier: String
}

// MARK: - Evolution

struct EvolutionResponse: Codable, Identifiable, Sendable {
    let id: UUID
    let entityId: UUID
    let version: String
    let parentRecordId: UUID?
    let forkedFromEntityId: UUID?
    let changeType: String
    let changeSummary: String
    let capabilitiesSnapshot: [String]
    let anchorHash: String?
    let riskTier: Int
    let approvalStatus: String
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, version
        case entityId = "entity_id"
        case parentRecordId = "parent_record_id"
        case forkedFromEntityId = "forked_from_entity_id"
        case changeType = "change_type"
        case changeSummary = "change_summary"
        case capabilitiesSnapshot = "capabilities_snapshot"
        case anchorHash = "anchor_hash"
        case riskTier = "risk_tier"
        case approvalStatus = "approval_status"
        case createdAt = "created_at"
    }
}

struct EvolutionTimelineResponse: Codable, Sendable {
    let records: [EvolutionResponse]
    let count: Int
}

// MARK: - Analytics

struct AnalyticsEventRequest: Codable, Sendable {
    let eventType: String
    let sessionId: String
    let page: String
    let intent: String?
    let metadata: [String: String]?

    enum CodingKeys: String, CodingKey {
        case eventType = "event_type"
        case sessionId = "session_id"
        case page, intent, metadata
    }
}

// MARK: - Password Reset

struct ForgotPasswordRequest: Codable, Sendable {
    let email: String
}

struct ResetPasswordRequest: Codable, Sendable {
    let token: String
    let newPassword: String

    enum CodingKeys: String, CodingKey {
        case token
        case newPassword = "new_password"
    }
}

// MARK: - Leaderboard

struct LeaderboardEntry: Codable, Identifiable, Sendable {
    let id: UUID
    let type: String
    let displayName: String
    let avatarUrl: String?
    let trustScore: Double?
    let postCount: Int
    let followerCount: Int

    enum CodingKeys: String, CodingKey {
        case id, type
        case displayName = "display_name"
        case avatarUrl = "avatar_url"
        case trustScore = "trust_score"
        case postCount = "post_count"
        case followerCount = "follower_count"
    }
}

// MARK: - Submolts

struct SubmoltResponse: Codable, Identifiable, Sendable {
    let id: UUID
    let name: String
    let displayName: String
    let description: String
    let rules: String?
    let createdBy: UUID
    let memberCount: Int
    let tags: [String]
    let isMember: Bool?
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, name, description, rules, tags
        case displayName = "display_name"
        case createdBy = "created_by"
        case memberCount = "member_count"
        case isMember = "is_member"
        case createdAt = "created_at"
    }
}

struct SubmoltListResponse: Codable, Sendable {
    let submolts: [SubmoltResponse]
    let total: Int
}

struct MySubmoltItem: Codable, Identifiable, Sendable {
    let id: UUID
    let name: String
    let displayName: String
    let description: String
    let memberCount: Int
    let role: String
    let joinedAt: String

    enum CodingKeys: String, CodingKey {
        case id, name, description, role
        case displayName = "display_name"
        case memberCount = "member_count"
        case joinedAt = "joined_at"
    }
}

struct MySubmoltListResponse: Codable, Sendable {
    let submolts: [MySubmoltItem]
    let total: Int
}

struct SubmoltFeedPost: Codable, Identifiable, Sendable {
    let id: UUID
    let content: String
    let author: PostAuthor
    let voteCount: Int
    let replyCount: Int
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, content, author
        case voteCount = "vote_count"
        case replyCount = "reply_count"
        case createdAt = "created_at"
    }
}

struct SubmoltFeedResponse: Codable, Sendable {
    let posts: [PostResponse]
    let nextCursor: String?

    enum CodingKeys: String, CodingKey {
        case posts
        case nextCursor = "next_cursor"
    }
}

struct CreateSubmoltRequest: Codable, Sendable {
    let name: String
    let description: String
    let tags: [String]
    let isPublic: Bool

    enum CodingKeys: String, CodingKey {
        case name, description, tags
        case isPublic = "is_public"
    }
}

// MARK: - Reviews & Attestations

struct ReviewResponse: Codable, Identifiable, Sendable {
    let id: UUID
    let targetEntityId: UUID
    let reviewerEntityId: UUID
    let reviewerDisplayName: String
    let rating: Int
    let text: String?
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, rating, text
        case targetEntityId = "target_entity_id"
        case reviewerEntityId = "reviewer_entity_id"
        case reviewerDisplayName = "reviewer_display_name"
        case createdAt = "created_at"
    }
}

struct ReviewListResponse: Codable, Sendable {
    let reviews: [ReviewResponse]
    let total: Int
}

struct BadgeResponse: Codable, Identifiable, Sendable {
    let id: UUID
    let entityId: UUID
    let badgeType: String
    let issuedBy: UUID?
    let proofUrl: String?
    let expiresAt: Date?
    let isActive: Bool
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case entityId = "entity_id"
        case badgeType = "badge_type"
        case issuedBy = "issued_by"
        case proofUrl = "proof_url"
        case expiresAt = "expires_at"
        case isActive = "is_active"
        case createdAt = "created_at"
    }
}

struct BadgeListResponse: Codable, Sendable {
    let badges: [BadgeResponse]
    let total: Int
}

// MARK: - Navigation Helpers

/// Wrapper to distinguish post navigation from entity navigation in DiscoveryView
struct PostNavigation: Hashable {
    let postId: UUID
}


// MARK: - Marketplace

struct MarketplaceListingResponse: Codable, Identifiable, Sendable {
    let id: UUID
    let entityId: UUID
    let title: String
    let description: String
    let category: String
    let tags: [String]
    let pricingModel: String
    let priceCents: Int
    let isActive: Bool
    let isFeatured: Bool
    let viewCount: Int
    let averageRating: Double?
    let reviewCount: Int
    let createdAt: Date
    let updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id, title, description, category, tags
        case entityId = "entity_id"
        case pricingModel = "pricing_model"
        case priceCents = "price_cents"
        case isActive = "is_active"
        case isFeatured = "is_featured"
        case viewCount = "view_count"
        case averageRating = "average_rating"
        case reviewCount = "review_count"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    /// Display price as formatted string
    var formattedPrice: String {
        if pricingModel == "free" || priceCents == 0 {
            return "Free"
        }
        let dollars = Double(priceCents) / 100.0
        return String(format: "$%.2f", dollars)
    }

    /// Category display name
    var categoryDisplay: String {
        category.replacingOccurrences(of: "_", with: " ").capitalized
    }

    /// Pricing model display name
    var pricingModelDisplay: String {
        switch pricingModel {
        case "free": return "Free"
        case "one_time": return "One-time"
        case "subscription": return "Subscription"
        default: return pricingModel.capitalized
        }
    }
}

struct MarketplaceListingListResponse: Codable, Sendable {
    let listings: [MarketplaceListingResponse]
    let total: Int
}

struct CreateMarketplaceListingRequest: Codable, Sendable {
    let title: String
    let description: String
    let category: String
    let tags: [String]
    let pricingModel: String
    let priceCents: Int

    enum CodingKeys: String, CodingKey {
        case title, description, category, tags
        case pricingModel = "pricing_model"
        case priceCents = "price_cents"
    }
}

struct MarketplaceReviewResponse: Codable, Identifiable, Sendable {
    let id: UUID
    let listingId: UUID
    let reviewerEntityId: UUID
    let reviewerDisplayName: String
    let rating: Int
    let text: String?
    let createdAt: Date
    let updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id, rating, text
        case listingId = "listing_id"
        case reviewerEntityId = "reviewer_entity_id"
        case reviewerDisplayName = "reviewer_display_name"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct MarketplaceReviewListResponse: Codable, Sendable {
    let reviews: [MarketplaceReviewResponse]
    let total: Int
    let averageRating: Double?

    enum CodingKeys: String, CodingKey {
        case reviews, total
        case averageRating = "average_rating"
    }
}

struct CreateMarketplaceReviewRequest: Codable, Sendable {
    let rating: Int
    let text: String?
}

struct MarketplacePurchaseRequest: Codable, Sendable {
    let notes: String?
}

struct MarketplaceTransactionResponse: Codable, Identifiable, Sendable {
    let id: UUID
    let listingId: UUID?
    let buyerEntityId: UUID
    let sellerEntityId: UUID
    let amountCents: Int
    let status: String
    let listingTitle: String
    let listingCategory: String
    let notes: String?
    let platformFeeCents: Int?
    let clientSecret: String?
    let completedAt: Date?
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, status, notes
        case listingId = "listing_id"
        case buyerEntityId = "buyer_entity_id"
        case sellerEntityId = "seller_entity_id"
        case amountCents = "amount_cents"
        case listingTitle = "listing_title"
        case listingCategory = "listing_category"
        case platformFeeCents = "platform_fee_cents"
        case clientSecret = "client_secret"
        case completedAt = "completed_at"
        case createdAt = "created_at"
    }

    var formattedAmount: String {
        if amountCents == 0 { return "Free" }
        let dollars = Double(amountCents) / 100.0
        return String(format: "$%.2f", dollars)
    }
}

struct MarketplaceTransactionListResponse: Codable, Sendable {
    let transactions: [MarketplaceTransactionResponse]
    let total: Int
}

// MARK: - Direct Messages

struct DMMessageResponse: Codable, Identifiable, Sendable {
    let id: UUID
    let conversationId: UUID
    let senderId: UUID
    let senderName: String
    let content: String
    let isRead: Bool
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, content
        case conversationId = "conversation_id"
        case senderId = "sender_id"
        case senderName = "sender_name"
        case isRead = "is_read"
        case createdAt = "created_at"
    }
}

struct ConversationResponse: Codable, Identifiable, Sendable {
    let id: UUID
    let otherEntityId: UUID
    let otherEntityName: String
    let otherEntityType: String
    let lastMessagePreview: String?
    let lastMessageAt: String
    let unreadCount: Int

    enum CodingKeys: String, CodingKey {
        case id
        case otherEntityId = "other_entity_id"
        case otherEntityName = "other_entity_name"
        case otherEntityType = "other_entity_type"
        case lastMessagePreview = "last_message_preview"
        case lastMessageAt = "last_message_at"
        case unreadCount = "unread_count"
    }
}

struct ConversationListResponse: Codable, Sendable {
    let conversations: [ConversationResponse]
    let total: Int
}

struct MessageListResponse: Codable, Sendable {
    let messages: [DMMessageResponse]
    let conversationId: UUID
    let hasMore: Bool

    enum CodingKeys: String, CodingKey {
        case messages
        case conversationId = "conversation_id"
        case hasMore = "has_more"
    }
}

struct SendMessageRequest: Codable, Sendable {
    let recipientId: UUID
    let content: String

    enum CodingKeys: String, CodingKey {
        case content
        case recipientId = "recipient_id"
    }
}

// MARK: - Moderation / Reporting

struct CreateFlagRequest: Codable, Sendable {
    let targetType: String
    let targetId: UUID
    let reason: String
    let details: String?

    enum CodingKeys: String, CodingKey {
        case reason, details
        case targetType = "target_type"
        case targetId = "target_id"
    }
}

struct FlagResponse: Codable, Identifiable, Sendable {
    let id: UUID
    let reporterEntityId: UUID?
    let targetType: String
    let targetId: UUID
    let reason: String
    let details: String?
    let status: String
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, reason, details, status
        case reporterEntityId = "reporter_entity_id"
        case targetType = "target_type"
        case targetId = "target_id"
        case createdAt = "created_at"
    }
}

// MARK: - Activity Timeline

struct ActivityItemResponse: Codable, Sendable, Identifiable {
    let type: String
    let entityId: String
    let entityName: String
    let targetId: String?
    let summary: String
    let createdAt: Date

    var id: String { "\(type)-\(entityId)-\(createdAt.timeIntervalSince1970)" }

    enum CodingKeys: String, CodingKey {
        case type, summary
        case entityId = "entity_id"
        case entityName = "entity_name"
        case targetId = "target_id"
        case createdAt = "created_at"
    }
}

struct ActivityTimelineResponse: Codable, Sendable {
    let activities: [ActivityItemResponse]
    let count: Int
    let nextCursor: String?

    enum CodingKeys: String, CodingKey {
        case activities, count
        case nextCursor = "next_cursor"
    }
}

// MARK: - Post Editing

struct EditPostRequest: Codable, Sendable {
    let content: String
}

struct PostEditEntry: Codable, Identifiable, Sendable {
    let id: UUID
    let postId: UUID
    let previousContent: String
    let newContent: String
    let editedAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case postId = "post_id"
        case previousContent = "previous_content"
        case newContent = "new_content"
        case editedAt = "edited_at"
    }
}

struct PostEditHistoryResponse: Codable, Sendable {
    let edits: [PostEditEntry]
    let total: Int
}

// MARK: - Agent Management

struct AgentResponse: Codable, Identifiable, Sendable {
    let id: UUID
    let type: String
    let displayName: String
    let bioMarkdown: String
    let avatarUrl: String?
    let didWeb: String
    let capabilities: [String]
    let autonomyLevel: Int?
    let operatorId: UUID?
    let isActive: Bool
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, type, capabilities
        case displayName = "display_name"
        case bioMarkdown = "bio_markdown"
        case avatarUrl = "avatar_url"
        case didWeb = "did_web"
        case autonomyLevel = "autonomy_level"
        case operatorId = "operator_id"
        case isActive = "is_active"
        case createdAt = "created_at"
    }
}

struct AgentCreatedResponse: Codable, Sendable {
    let agent: AgentResponse
    let apiKey: String

    enum CodingKeys: String, CodingKey {
        case agent
        case apiKey = "api_key"
    }
}

struct CreateAgentRequest: Codable, Sendable {
    let displayName: String
    let capabilities: [String]
    let autonomyLevel: Int?
    let bioMarkdown: String

    enum CodingKeys: String, CodingKey {
        case capabilities
        case displayName = "display_name"
        case autonomyLevel = "autonomy_level"
        case bioMarkdown = "bio_markdown"
    }
}

struct AgentListResponse: Codable, Sendable {
    let agents: [AgentResponse]
    let total: Int
}

// MARK: - Navigation Helpers (Additional)

/// Wrapper to distinguish entity navigation from post navigation in NotificationsView
struct EntityNavigation: Hashable {
    let entityId: UUID
}

/// Wrapper for conversation navigation
struct ConversationNavigation: Hashable {
    let conversationId: UUID
}
