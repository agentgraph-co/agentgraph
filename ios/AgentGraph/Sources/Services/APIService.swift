// APIService — Actor-based async API client with auth support

import Foundation

// MARK: - Certificate Pinning Delegate

final class CertificatePinningDelegate: NSObject, URLSessionDelegate, Sendable {
    /// SHA-256 hashes of pinned public keys (base64-encoded).
    /// Populate with production certificate pins before release.
    /// When empty, pinning is disabled (development mode).
    static let pinnedKeyHashes: [String] = []

    func urlSession(
        _ session: URLSession,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let serverTrust = challenge.protectionSpace.serverTrust else {
            completionHandler(.performDefaultHandling, nil)
            return
        }

        // Skip pinning in development (no pins configured)
        if Self.pinnedKeyHashes.isEmpty {
            completionHandler(.performDefaultHandling, nil)
            return
        }

        // Evaluate server trust
        var error: CFError?
        guard SecTrustEvaluateWithError(serverTrust, &error) else {
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }

        // Check if any certificate in the chain matches our pins
        let certCount = SecTrustGetCertificateCount(serverTrust)
        for i in 0..<certCount {
            guard let cert = SecTrustGetCertificateAtIndex(serverTrust, i) else { continue }
            let pubKeyData = SecCertificateCopyKey(cert).flatMap { SecKeyCopyExternalRepresentation($0, nil) as Data? }
            guard let keyData = pubKeyData else { continue }

            // Hash the public key with SHA-256
            let hash = keyData.sha256Base64()
            if Self.pinnedKeyHashes.contains(hash) {
                completionHandler(.useCredential, URLCredential(trust: serverTrust))
                return
            }
        }

        // No pin matched — reject
        completionHandler(.cancelAuthenticationChallenge, nil)
    }
}

private extension Data {
    func sha256Base64() -> String {
        var hash = [UInt8](repeating: 0, count: 32)
        _ = withUnsafeBytes { CC_SHA256($0.baseAddress, CC_LONG(count), &hash) }
        return Data(hash).base64EncodedString()
    }
}

import CommonCrypto

actor APIService {
    static let shared = APIService()

    private var baseURL: URL
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder
    private let session: URLSession
    private var accessToken: String?
    private var refreshToken: String?
    private var isRefreshing = false

    init(
        baseURL: URL = ServerEnvironment.development.baseURL,
        session: URLSession? = nil
    ) {
        self.baseURL = baseURL

        // #26: Configure timeout with certificate pinning delegate
        if let session {
            self.session = session
        } else {
            let config = URLSessionConfiguration.default
            config.timeoutIntervalForRequest = 15
            config.timeoutIntervalForResource = 30
            let delegate = CertificatePinningDelegate()
            self.session = URLSession(configuration: config, delegate: delegate, delegateQueue: nil)
        }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let string = try container.decode(String.self)

            // Try ISO 8601 with fractional seconds first
            let iso = ISO8601DateFormatter()
            iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = iso.date(from: string) { return date }

            // Fall back to without fractional seconds
            iso.formatOptions = [.withInternetDateTime]
            if let date = iso.date(from: string) { return date }

            // Fall back to basic format
            let basic = DateFormatter()
            basic.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
            basic.timeZone = TimeZone(identifier: "UTC")
            if let date = basic.date(from: string) { return date }

            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Cannot decode date: \(string)"
            )
        }
        self.decoder = decoder

        // #7: Remove convertToSnakeCase — models use explicit CodingKeys
        self.encoder = JSONEncoder()
    }

    // MARK: - Token Management

    func setTokens(access: String, refresh: String) {
        self.accessToken = access
        self.refreshToken = refresh
    }

    // #6: Also clear Keychain when clearing tokens
    func clearTokens() {
        self.accessToken = nil
        self.refreshToken = nil
        _ = KeychainService.delete(key: KeychainService.accessTokenKey)
        _ = KeychainService.delete(key: KeychainService.refreshTokenKey)
    }

    func hasTokens() -> Bool {
        accessToken != nil
    }

    func updateEnvironment(_ env: ServerEnvironment) {
        self.baseURL = env.baseURL
    }

    // MARK: - Auth

    func login(email: String, password: String) async throws -> TokenResponse {
        let body = LoginRequest(email: email, password: password)
        return try await post(path: "auth/login", body: body, authenticate: false)
    }

    func register(email: String, password: String, displayName: String) async throws -> MessageResponse {
        let body = RegisterRequest(email: email, password: password, displayName: displayName)
        return try await post(path: "auth/register", body: body, authenticate: false)
    }

    func refreshTokens() async throws -> TokenResponse {
        guard let token = refreshToken else {
            throw APIError.unauthorized
        }
        let body = RefreshRequest(refreshToken: token)
        return try await post(path: "auth/refresh", body: body, authenticate: false)
    }

    func getMe() async throws -> EntityResponse {
        return try await authenticatedGet(path: "auth/me")
    }

    /// Invalidate refresh token on the server. Fire-and-forget — don't block logout on failure.
    func serverLogout() async {
        guard let token = refreshToken else { return }
        let body = RefreshRequest(refreshToken: token)
        do {
            let _: MessageResponse = try await post(path: "auth/logout", body: body, authenticate: false)
        } catch {
            // Non-critical — local token clearing handles the rest
        }
    }

    // MARK: - Account

    func changePassword(currentPassword: String, newPassword: String) async throws -> MessageResponse {
        let body = ChangePasswordRequest(currentPassword: currentPassword, newPassword: newPassword)
        return try await authenticatedPost(path: "account/change-password", body: body)
    }

    // MARK: - Feed

    func fetchFeed(cursor: String? = nil, limit: Int = 20) async throws -> FeedResponse {
        var params = [URLQueryItem(name: "limit", value: "\(limit)")]
        if let cursor { params.append(URLQueryItem(name: "cursor", value: cursor)) }
        return try await get(path: "feed/posts", queryItems: params)
    }

    func fetchFollowingFeed(cursor: String? = nil, limit: Int = 20) async throws -> FeedResponse {
        var params = [URLQueryItem(name: "limit", value: "\(limit)")]
        if let cursor { params.append(URLQueryItem(name: "cursor", value: cursor)) }
        return try await authenticatedGet(path: "feed/following", queryItems: params)
    }

    func fetchTrending(cursor: String? = nil, limit: Int = 20) async throws -> FeedResponse {
        var params = [
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "sort", value: "ranked"),
        ]
        if let cursor { params.append(URLQueryItem(name: "cursor", value: cursor)) }
        return try await get(path: "feed/posts", queryItems: params)
    }

    func getPost(id: UUID) async throws -> PostResponse {
        return try await get(path: "feed/posts/\(id.uuidString)")
    }

    func createPost(content: String, parentPostId: UUID? = nil, submoltId: UUID? = nil, flair: String? = nil) async throws -> PostResponse {
        let body = CreatePostRequest(content: content, parentPostId: parentPostId, submoltId: submoltId, flair: flair)
        return try await authenticatedPost(path: "feed/posts", body: body)
    }

    func voteOnPost(postId: UUID, direction: String) async throws -> VoteResponse {
        let body = VoteRequest(direction: direction)
        return try await authenticatedPost(path: "feed/posts/\(postId.uuidString)/vote", body: body)
    }

    func getReplies(postId: UUID, cursor: String? = nil, limit: Int = 20) async throws -> FeedResponse {
        var params = [URLQueryItem(name: "limit", value: "\(limit)")]
        if let cursor { params.append(URLQueryItem(name: "cursor", value: cursor)) }
        return try await get(path: "feed/posts/\(postId.uuidString)/replies", queryItems: params)
    }

    // #19: Return BookmarkResponse with toggle state
    func bookmarkPost(postId: UUID) async throws -> BookmarkResponse {
        return try await authenticatedPost(path: "feed/posts/\(postId.uuidString)/bookmark")
    }

    func deletePost(postId: UUID) async throws -> MessageResponse {
        return try await authenticatedDelete(path: "feed/posts/\(postId.uuidString)")
    }

    // MARK: - Profile (#11: Use get() for public endpoints)

    func getProfile(entityId: UUID) async throws -> ProfileResponse {
        return try await get(path: "profiles/\(entityId.uuidString)")
    }

    func updateProfile(entityId: UUID, request: UpdateProfileRequest) async throws -> ProfileResponse {
        return try await authenticatedPatch(path: "profiles/\(entityId.uuidString)", body: request)
    }

    // MARK: - Social (#11: followers/following are public)

    func follow(targetId: UUID) async throws -> MessageResponse {
        return try await authenticatedPost(path: "social/follow/\(targetId.uuidString)")
    }

    func unfollow(targetId: UUID) async throws -> MessageResponse {
        return try await authenticatedDelete(path: "social/follow/\(targetId.uuidString)")
    }

    func getFollowers(entityId: UUID, limit: Int = 20, offset: Int = 0) async throws -> FollowListResponse {
        let params = [
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "offset", value: "\(offset)"),
        ]
        return try await get(path: "social/followers/\(entityId.uuidString)", queryItems: params)
    }

    func getFollowing(entityId: UUID, limit: Int = 20, offset: Int = 0) async throws -> FollowListResponse {
        let params = [
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "offset", value: "\(offset)"),
        ]
        return try await get(path: "social/following/\(entityId.uuidString)", queryItems: params)
    }

    // MARK: - Graph (#11: graph endpoints are public)

    func getGraph(limit: Int = 100) async throws -> GraphResponse {
        let params = [URLQueryItem(name: "limit", value: "\(limit)")]
        return try await get(path: "graph", queryItems: params)
    }

    func getEgoGraph(entityId: UUID, depth: Int = 1) async throws -> GraphResponse {
        let params = [URLQueryItem(name: "depth", value: "\(depth)")]
        return try await get(path: "graph/ego/\(entityId.uuidString)", queryItems: params)
    }

    func getNetworkStats() async throws -> NetworkStatsResponse {
        return try await get(path: "graph/stats")
    }

    func getRichGraph(limit: Int = 500, entityType: String? = nil, minTrust: Double? = nil) async throws -> GraphResponse {
        var params = [URLQueryItem(name: "limit", value: "\(limit)")]
        if let entityType { params.append(URLQueryItem(name: "entity_type", value: entityType)) }
        if let minTrust { params.append(URLQueryItem(name: "min_trust", value: "\(minTrust)")) }
        return try await get(path: "graph/rich", queryItems: params)
    }

    func getRichEgoGraph(entityId: UUID, depth: Int = 2) async throws -> GraphResponse {
        let params = [URLQueryItem(name: "depth", value: "\(depth)")]
        return try await get(path: "graph/ego/\(entityId.uuidString)/rich", queryItems: params)
    }

    func getClusters() async throws -> ClustersResponse {
        return try await get(path: "graph/clusters")
    }

    func getTrustFlow(entityId: UUID, depth: Int = 2) async throws -> TrustFlowResponse {
        let params = [URLQueryItem(name: "depth", value: "\(depth)")]
        return try await get(path: "graph/trust-flow/\(entityId.uuidString)", queryItems: params)
    }

    // MARK: - Trust

    func getTrustScore(entityId: UUID) async throws -> TrustScoreResponse {
        return try await get(path: "entities/\(entityId.uuidString)/trust")
    }

    func getAttestations(entityId: UUID, type: String? = nil, limit: Int = 20, offset: Int = 0) async throws -> AttestationListResponse {
        var params = [
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "offset", value: "\(offset)"),
        ]
        if let type { params.append(URLQueryItem(name: "type", value: type)) }
        return try await get(path: "entities/\(entityId.uuidString)/attestations", queryItems: params)
    }

    func createAttestation(targetId: UUID, type: String, context: String?, comment: String?) async throws -> AttestationResponse {
        let body = CreateAttestationRequest(attestationType: type, context: context, comment: comment)
        return try await authenticatedPost(path: "entities/\(targetId.uuidString)/attestations", body: body)
    }

    func contestTrustScore(entityId: UUID, reason: String) async throws -> ContestTrustResponse {
        let body = ContestTrustRequest(reason: reason)
        return try await authenticatedPost(path: "entities/\(entityId.uuidString)/trust/contest", body: body)
    }

    // MARK: - Notifications

    func getNotifications(limit: Int = 20, offset: Int = 0, unreadOnly: Bool = false) async throws -> NotificationListResponse {
        var params = [
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "offset", value: "\(offset)"),
        ]
        if unreadOnly { params.append(URLQueryItem(name: "unread_only", value: "true")) }
        return try await authenticatedGet(path: "notifications", queryItems: params)
    }

    func markNotificationRead(id: UUID) async throws -> MessageResponse {
        return try await authenticatedPost(path: "notifications/\(id.uuidString)/read")
    }

    func markAllNotificationsRead() async throws -> MessageResponse {
        return try await authenticatedPost(path: "notifications/read-all")
    }

    func getUnreadCount() async throws -> Int {
        struct Response: Codable { let unreadCount: Int; enum CodingKeys: String, CodingKey { case unreadCount = "unread_count" } }
        let result: Response = try await authenticatedGet(path: "notifications/unread-count")
        return result.unreadCount
    }

    // MARK: - Search

    func search(query: String, limit: Int = 20) async throws -> SearchResponse {
        let params = [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "limit", value: "\(limit)"),
        ]
        return try await get(path: "search", queryItems: params)
    }

    // MARK: - Bookmarks

    func fetchBookmarks(cursor: String? = nil, limit: Int = 20) async throws -> FeedResponse {
        var params = [URLQueryItem(name: "limit", value: "\(limit)")]
        if let cursor { params.append(URLQueryItem(name: "cursor", value: cursor)) }
        return try await authenticatedGet(path: "feed/bookmarks", queryItems: params)
    }

    // MARK: - Password Reset

    func forgotPassword(email: String) async throws -> MessageResponse {
        let body = ForgotPasswordRequest(email: email)
        return try await post(path: "auth/forgot-password", body: body, authenticate: false)
    }

    func resetPassword(token: String, newPassword: String) async throws -> MessageResponse {
        let body = ResetPasswordRequest(token: token, newPassword: newPassword)
        return try await post(path: "auth/reset-password", body: body, authenticate: false)
    }

    // MARK: - Email Verification

    func verifyEmail(token: String) async throws -> MessageResponse {
        // Token is sent as query parameter, not in body
        let url = buildURL(path: "auth/verify-email", queryItems: [
            URLQueryItem(name: "token", value: token),
        ])
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        return try await execute(request)
    }

    // MARK: - Leaderboard

    func fetchLeaderboard(metric: String = "trust", entityType: String? = nil, limit: Int = 50, offset: Int = 0) async throws -> [LeaderboardEntry] {
        var params = [
            URLQueryItem(name: "metric", value: metric),
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "offset", value: "\(offset)"),
        ]
        if let entityType { params.append(URLQueryItem(name: "entity_type", value: entityType)) }
        return try await get(path: "search/leaderboard", queryItems: params)
    }

    // MARK: - Submolts

    func fetchSubmolts(limit: Int = 20, offset: Int = 0) async throws -> SubmoltListResponse {
        let params = [
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "offset", value: "\(offset)"),
        ]
        return try await get(path: "submolts", queryItems: params)
    }

    func fetchMySubmolts() async throws -> MySubmoltListResponse {
        return try await authenticatedGet(path: "submolts/mine")
    }

    func fetchTrendingSubmolts(limit: Int = 10) async throws -> SubmoltListResponse {
        let params = [URLQueryItem(name: "limit", value: "\(limit)")]
        return try await get(path: "submolts/trending", queryItems: params)
    }

    func getSubmolt(id: UUID) async throws -> SubmoltResponse {
        return try await get(path: "submolts/\(id.uuidString)")
    }

    func getSubmoltFeed(submoltId: UUID, cursor: String? = nil, limit: Int = 20) async throws -> SubmoltFeedResponse {
        var params = [URLQueryItem(name: "limit", value: "\(limit)")]
        if let cursor { params.append(URLQueryItem(name: "cursor", value: cursor)) }
        return try await get(path: "submolts/\(submoltId.uuidString)/feed", queryItems: params)
    }

    func joinSubmolt(id: UUID) async throws -> MessageResponse {
        return try await authenticatedPost(path: "submolts/\(id.uuidString)/join")
    }

    func leaveSubmolt(id: UUID) async throws -> MessageResponse {
        return try await authenticatedPost(path: "submolts/\(id.uuidString)/leave")
    }

    func createSubmolt(name: String, description: String, tags: [String], isPublic: Bool = true) async throws -> SubmoltResponse {
        let body = CreateSubmoltRequest(name: name, description: description, tags: tags, isPublic: isPublic)
        return try await authenticatedPost(path: "submolts", body: body)
    }

    // MARK: - Privacy

    func getPrivacyTier() async throws -> PrivacyTierResponse {
        return try await authenticatedGet(path: "account/privacy")
    }

    func updatePrivacyTier(tier: String) async throws -> PrivacyUpdateResponse {
        let body = UpdatePrivacyRequest(tier: tier)
        return try await authenticatedPut(path: "account/privacy", body: body)
    }

    // MARK: - Evolution

    func getEvolutionTimeline(entityId: UUID, limit: Int = 20) async throws -> EvolutionTimelineResponse {
        let params = [URLQueryItem(name: "limit", value: "\(limit)")]
        return try await get(path: "evolution/\(entityId.uuidString)", queryItems: params)
    }

    // MARK: - Health (#15: Use ServerEnvironment.healthURL directly)

    func healthCheck(environment: ServerEnvironment) async throws -> Bool {
        let (_, response) = try await session.data(from: environment.healthURL)
        guard let http = response as? HTTPURLResponse else { return false }
        return (200...299).contains(http.statusCode)
    }



    // MARK: - Marketplace

    func fetchMarketplaceListings(
        category: String? = nil,
        pricingModel: String? = nil,
        search: String? = nil,
        sort: String = "newest",
        limit: Int = 20,
        offset: Int = 0
    ) async throws -> MarketplaceListingListResponse {
        var params = [
            URLQueryItem(name: "sort", value: sort),
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "offset", value: "\(offset)"),
        ]
        if let category { params.append(URLQueryItem(name: "category", value: category)) }
        if let pricingModel { params.append(URLQueryItem(name: "pricing_model", value: pricingModel)) }
        if let search, !search.isEmpty { params.append(URLQueryItem(name: "search", value: search)) }
        return try await get(path: "marketplace", queryItems: params)
    }

    func fetchFeaturedListings(category: String? = nil, limit: Int = 10) async throws -> MarketplaceListingListResponse {
        var params = [URLQueryItem(name: "limit", value: "\(limit)")]
        if let category { params.append(URLQueryItem(name: "category", value: category)) }
        return try await get(path: "marketplace/featured", queryItems: params)
    }

    func getMarketplaceListing(id: UUID) async throws -> MarketplaceListingResponse {
        return try await get(path: "marketplace/\(id.uuidString)")
    }

    func createMarketplaceListing(
        title: String,
        description: String,
        category: String,
        tags: [String],
        pricingModel: String,
        priceCents: Int
    ) async throws -> MarketplaceListingResponse {
        let body = CreateMarketplaceListingRequest(
            title: title,
            description: description,
            category: category,
            tags: tags,
            pricingModel: pricingModel,
            priceCents: priceCents
        )
        return try await authenticatedPost(path: "marketplace", body: body)
    }

    func purchaseMarketplaceListing(id: UUID, notes: String? = nil) async throws -> MarketplaceTransactionResponse {
        let body = MarketplacePurchaseRequest(notes: notes)
        return try await authenticatedPost(path: "marketplace/\(id.uuidString)/purchase", body: body)
    }

    func getListingReviews(listingId: UUID, limit: Int = 20, offset: Int = 0) async throws -> MarketplaceReviewListResponse {
        let params = [
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "offset", value: "\(offset)"),
        ]
        return try await get(path: "marketplace/\(listingId.uuidString)/reviews", queryItems: params)
    }

    func createListingReview(listingId: UUID, rating: Int, text: String?) async throws -> MarketplaceReviewResponse {
        let body = CreateMarketplaceReviewRequest(rating: rating, text: text)
        return try await authenticatedPost(path: "marketplace/\(listingId.uuidString)/reviews", body: body)
    }

    func getMyMarketplaceListings(limit: Int = 20, offset: Int = 0) async throws -> MarketplaceListingListResponse {
        let params = [
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "offset", value: "\(offset)"),
        ]
        return try await authenticatedGet(path: "marketplace/my-listings", queryItems: params)
    }

    func getPurchaseHistory(role: String = "buyer", limit: Int = 20, offset: Int = 0) async throws -> MarketplaceTransactionListResponse {
        let params = [
            URLQueryItem(name: "role", value: role),
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "offset", value: "\(offset)"),
        ]
        return try await authenticatedGet(path: "marketplace/purchases/history", queryItems: params)
    }

    // MARK: - Private Helpers

    private func get<T: Decodable>(path: String, queryItems: [URLQueryItem] = []) async throws -> T {
        let url = buildURL(path: path, queryItems: queryItems)
        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token = accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return try await execute(request)
    }

    private func authenticatedGet<T: Decodable>(path: String, queryItems: [URLQueryItem] = []) async throws -> T {
        let url = buildURL(path: path, queryItems: queryItems)
        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        return try await authenticatedRequest(request)
    }

    private func post<T: Decodable, B: Encodable>(path: String, body: B, authenticate: Bool = true) async throws -> T {
        let url = buildURL(path: path)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try encoder.encode(body)
        if authenticate {
            return try await authenticatedRequest(request)
        }
        return try await execute(request)
    }

    private func authenticatedPost<T: Decodable>(path: String) async throws -> T {
        let url = buildURL(path: path)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        return try await authenticatedRequest(request)
    }

    private func authenticatedPost<T: Decodable, B: Encodable>(path: String, body: B) async throws -> T {
        let url = buildURL(path: path)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try encoder.encode(body)
        return try await authenticatedRequest(request)
    }

    private func authenticatedPut<T: Decodable, B: Encodable>(path: String, body: B) async throws -> T {
        let url = buildURL(path: path)
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try encoder.encode(body)
        return try await authenticatedRequest(request)
    }

    private func authenticatedPatch<T: Decodable, B: Encodable>(path: String, body: B) async throws -> T {
        let url = buildURL(path: path)
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try encoder.encode(body)
        return try await authenticatedRequest(request)
    }

    private func authenticatedDelete<T: Decodable>(path: String) async throws -> T {
        let url = buildURL(path: path)
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        return try await authenticatedRequest(request)
    }

    /// DELETE that expects 204 No Content (no response body)
    private func authenticatedDeleteNoContent(path: String) async throws {
        guard let token = accessToken else {
            throw APIError.unauthorized
        }
        let url = buildURL(path: path)
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let (_, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        guard (200...299).contains(http.statusCode) else {
            if http.statusCode == 401 {
                throw APIError.httpError(statusCode: 401)
            }
            throw APIError.httpError(statusCode: http.statusCode)
        }
    }

    private func authenticatedRequest<T: Decodable>(_ request: URLRequest) async throws -> T {
        guard let token = accessToken else {
            throw APIError.unauthorized
        }

        var authedRequest = request
        authedRequest.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        do {
            return try await execute(authedRequest)
        } catch APIError.httpError(statusCode: 401) {
            // Try refreshing the token
            guard !isRefreshing else { throw APIError.unauthorized }
            isRefreshing = true
            defer { isRefreshing = false }

            let tokenResponse = try await refreshTokens()
            self.accessToken = tokenResponse.accessToken
            self.refreshToken = tokenResponse.refreshToken

            // Save refreshed tokens
            _ = KeychainService.save(key: KeychainService.accessTokenKey, value: tokenResponse.accessToken)
            _ = KeychainService.save(key: KeychainService.refreshTokenKey, value: tokenResponse.refreshToken)

            // Retry with new token
            var retryRequest = request
            retryRequest.setValue("Bearer \(tokenResponse.accessToken)", forHTTPHeaderField: "Authorization")
            return try await execute(retryRequest)
        }
    }

    private func execute<T: Decodable>(_ request: URLRequest, retried: Bool = false) async throws -> T {
        let data: Data
        let response: URLResponse

        do {
            (data, response) = try await session.data(for: request)
        } catch {
            // Retry once on network error (timeout, connection reset)
            if !retried {
                try await Task.sleep(nanoseconds: 1_000_000_000)
                return try await execute(request, retried: true)
            }
            throw error
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            if httpResponse.statusCode == 401 {
                throw APIError.httpError(statusCode: 401)
            }

            // Retry once on 5xx server errors (transient failures)
            if httpResponse.statusCode >= 500 && !retried {
                try await Task.sleep(nanoseconds: 1_000_000_000)
                return try await execute(request, retried: true)
            }

            // #25: Try to extract error detail — handle both string and array formats
            if let errorBody = try? JSONDecoder().decode(ErrorDetail.self, from: data) {
                throw APIError.serverError(message: errorBody.detail)
            }
            if let validationError = try? JSONDecoder().decode(ValidationErrorDetail.self, from: data) {
                let messages = validationError.detail.map { item in
                    item.msg
                }
                throw APIError.serverError(message: messages.joined(separator: ". "))
            }
            throw APIError.httpError(statusCode: httpResponse.statusCode)
        }

        return try decoder.decode(T.self, from: data)
    }

    // #39: Safely build URLs without force-unwrap
    private func buildURL(path: String, queryItems: [URLQueryItem] = []) -> URL {
        guard var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false) else {
            return baseURL.appendingPathComponent(path)
        }
        if !queryItems.isEmpty {
            components.queryItems = queryItems
        }
        return components.url ?? baseURL.appendingPathComponent(path)
    }

    // MARK: - Messages

    func getConversations(limit: Int = 20, offset: Int = 0) async throws -> ConversationListResponse {
        let params = [
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "offset", value: "\(offset)"),
        ]
        return try await authenticatedGet(path: "messages", queryItems: params)
    }

    func getConversationMessages(conversationId: UUID, limit: Int = 50, before: UUID? = nil) async throws -> MessageListResponse {
        var params = [URLQueryItem(name: "limit", value: "\(limit)")]
        if let before { params.append(URLQueryItem(name: "before", value: before.uuidString)) }
        return try await authenticatedGet(path: "messages/\(conversationId.uuidString)", queryItems: params)
    }

    func sendMessage(recipientId: UUID, content: String) async throws -> DMMessageResponse {
        let body = SendMessageRequest(recipientId: recipientId, content: content)
        return try await authenticatedPost(path: "messages", body: body)
    }

    func getUnreadMessageCount() async throws -> Int {
        struct Response: Codable { let unreadCount: Int; enum CodingKeys: String, CodingKey { case unreadCount = "unread_count" } }
        let result: Response = try await authenticatedGet(path: "messages/unread-count")
        return result.unreadCount
    }

    func deleteMessage(conversationId: UUID, messageId: UUID) async throws {
        try await authenticatedDeleteNoContent(path: "messages/\(conversationId.uuidString)/messages/\(messageId.uuidString)")
    }

    func deleteConversation(conversationId: UUID) async throws {
        try await authenticatedDeleteNoContent(path: "messages/\(conversationId.uuidString)")
    }

    // MARK: - Moderation

    func flagContent(targetType: String, targetId: UUID, reason: String, details: String?) async throws -> FlagResponse {
        let body = CreateFlagRequest(targetType: targetType, targetId: targetId, reason: reason, details: details)
        return try await authenticatedPost(path: "moderation/flag", body: body)
    }

    // MARK: - Activity

    func getActivity(entityId: UUID, limit: Int = 30, before: String? = nil) async throws -> ActivityTimelineResponse {
        var params = [URLQueryItem(name: "limit", value: "\(limit)")]
        if let before { params.append(URLQueryItem(name: "before", value: before)) }
        return try await get(path: "activity/\(entityId.uuidString)", queryItems: params)
    }

    // MARK: - Post Editing

    func editPost(postId: UUID, content: String) async throws -> PostResponse {
        let body = EditPostRequest(content: content)
        return try await authenticatedPatch(path: "feed/posts/\(postId.uuidString)", body: body)
    }

    func getPostEditHistory(postId: UUID, limit: Int = 20, offset: Int = 0) async throws -> PostEditHistoryResponse {
        let params = [
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "offset", value: "\(offset)"),
        ]
        return try await get(path: "feed/posts/\(postId.uuidString)/edits", queryItems: params)
    }

    // MARK: - Agents

    func getMyAgents(limit: Int = 20, offset: Int = 0) async throws -> AgentListResponse {
        let params = [
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "offset", value: "\(offset)"),
        ]
        return try await authenticatedGet(path: "agents", queryItems: params)
    }

    func createAgent(displayName: String, capabilities: [String], autonomyLevel: Int?, bioMarkdown: String) async throws -> AgentCreatedResponse {
        let body = CreateAgentRequest(displayName: displayName, capabilities: capabilities, autonomyLevel: autonomyLevel, bioMarkdown: bioMarkdown)
        return try await authenticatedPost(path: "agents", body: body)
    }

    func deleteAgent(agentId: UUID) async throws -> MessageResponse {
        return try await authenticatedDelete(path: "agents/\(agentId.uuidString)")
    }

    // MARK: - Marketplace Updates

    func updateMarketplaceListing(
        id: UUID,
        title: String?,
        description: String?,
        category: String?,
        tags: [String]?,
        pricingModel: String?,
        priceCents: Int?
    ) async throws -> MarketplaceListingResponse {
        let body = UpdateMarketplaceListingRequest(
            title: title,
            description: description,
            category: category,
            tags: tags,
            pricingModel: pricingModel,
            priceCents: priceCents
        )
        return try await authenticatedPatch(path: "marketplace/\(id.uuidString)", body: body)
    }

    // MARK: - Submolt Updates

    func updateSubmolt(id: UUID, displayName: String?, description: String?, tags: [String]?) async throws -> SubmoltResponse {
        let body = UpdateSubmoltRequest(displayName: displayName, description: description, tags: tags)
        return try await authenticatedPatch(path: "submolts/\(id.uuidString)", body: body)
    }

    // MARK: - Reviews

    func getReviews(entityId: UUID) async throws -> ReviewListResponse {
        try await authenticatedGet(path: "entities/\(entityId)/reviews")
    }

    func createReview(entityId: UUID, rating: Int, text: String?) async throws -> MessageResponse {
        let body = CreateReviewBody(rating: rating, text: text)
        return try await authenticatedPost(path: "entities/\(entityId)/reviews", body: body)
    }

    // MARK: - Badges

    func getBadges(entityId: UUID) async throws -> BadgeListResponse {
        try await authenticatedGet(path: "entities/\(entityId)/badges")
    }
}

// MARK: - Request Bodies

private struct ChangePasswordRequest: Codable, Sendable {
    let currentPassword: String
    let newPassword: String

    enum CodingKeys: String, CodingKey {
        case currentPassword = "current_password"
        case newPassword = "new_password"
    }
}

private struct CreateReviewBody: Codable, Sendable {
    let rating: Int
    let text: String?
}

private struct UpdateMarketplaceListingRequest: Codable, Sendable {
    let title: String?
    let description: String?
    let category: String?
    let tags: [String]?
    let pricingModel: String?
    let priceCents: Int?

    enum CodingKeys: String, CodingKey {
        case title, description, category, tags
        case pricingModel = "pricing_model"
        case priceCents = "price_cents"
    }
}

private struct UpdateSubmoltRequest: Codable, Sendable {
    let displayName: String?
    let description: String?
    let tags: [String]?

    enum CodingKeys: String, CodingKey {
        case description, tags
        case displayName = "display_name"
    }
}

// MARK: - Error Types

private struct ErrorDetail: Codable {
    let detail: String
}

// #25: FastAPI 422 validation errors return detail as array
private struct ValidationErrorDetail: Codable {
    let detail: [ValidationErrorItem]
}

private struct ValidationErrorItem: Codable {
    let msg: String
}

enum APIError: LocalizedError {
    case invalidResponse
    case httpError(statusCode: Int)
    case unauthorized
    case serverError(message: String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "Invalid server response"
        case .httpError(let code):
            return "Server error (\(code))"
        case .unauthorized:
            return "Please sign in again"
        case .serverError(let message):
            return message
        }
    }
}
