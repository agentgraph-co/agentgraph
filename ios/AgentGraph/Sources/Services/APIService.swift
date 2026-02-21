// APIService — Actor-based async API client with auth support

import Foundation

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
        session: URLSession = .shared
    ) {
        self.baseURL = baseURL
        self.session = session

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

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        self.encoder = encoder
    }

    // MARK: - Token Management

    func setTokens(access: String, refresh: String) {
        self.accessToken = access
        self.refreshToken = refresh
    }

    func clearTokens() {
        self.accessToken = nil
        self.refreshToken = nil
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
        // Use unauthenticated request for refresh
        return try await post(path: "auth/refresh", body: body, authenticate: false)
    }

    func getMe() async throws -> EntityResponse {
        return try await authenticatedGet(path: "auth/me")
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

    func bookmarkPost(postId: UUID) async throws -> MessageResponse {
        return try await authenticatedPost(path: "feed/posts/\(postId.uuidString)/bookmark")
    }

    func deletePost(postId: UUID) async throws -> MessageResponse {
        return try await authenticatedDelete(path: "feed/posts/\(postId.uuidString)")
    }

    // MARK: - Profile

    func getProfile(entityId: UUID) async throws -> ProfileResponse {
        return try await authenticatedGet(path: "profiles/\(entityId.uuidString)")
    }

    func updateProfile(entityId: UUID, request: UpdateProfileRequest) async throws -> ProfileResponse {
        return try await authenticatedPatch(path: "profiles/\(entityId.uuidString)", body: request)
    }

    // MARK: - Social

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
        return try await authenticatedGet(path: "social/followers/\(entityId.uuidString)", queryItems: params)
    }

    func getFollowing(entityId: UUID, limit: Int = 20, offset: Int = 0) async throws -> FollowListResponse {
        let params = [
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "offset", value: "\(offset)"),
        ]
        return try await authenticatedGet(path: "social/following/\(entityId.uuidString)", queryItems: params)
    }

    // MARK: - Graph

    func getGraph(limit: Int = 100) async throws -> GraphResponse {
        let params = [URLQueryItem(name: "limit", value: "\(limit)")]
        return try await authenticatedGet(path: "graph", queryItems: params)
    }

    func getEgoGraph(entityId: UUID, depth: Int = 1) async throws -> GraphResponse {
        let params = [URLQueryItem(name: "depth", value: "\(depth)")]
        return try await authenticatedGet(path: "graph/ego/\(entityId.uuidString)", queryItems: params)
    }

    func getNetworkStats() async throws -> NetworkStatsResponse {
        return try await authenticatedGet(path: "graph/stats")
    }

    // MARK: - Trust

    func getTrustScore(entityId: UUID) async throws -> TrustScoreResponse {
        return try await get(path: "entities/\(entityId.uuidString)/trust")
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

    // MARK: - Evolution

    func getEvolutionTimeline(entityId: UUID, limit: Int = 20) async throws -> EvolutionTimelineResponse {
        let params = [URLQueryItem(name: "limit", value: "\(limit)")]
        return try await get(path: "evolution/\(entityId.uuidString)", queryItems: params)
    }

    // MARK: - Health

    func healthCheck() async throws -> Bool {
        let url = baseURL.deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("health")
        let (_, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse else { return false }
        return (200...299).contains(http.statusCode)
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

    private func execute<T: Decodable>(_ request: URLRequest) async throws -> T {
        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            if httpResponse.statusCode == 401 {
                throw APIError.httpError(statusCode: 401)
            }
            // Try to extract error detail from response
            if let errorBody = try? JSONDecoder().decode(ErrorDetail.self, from: data) {
                throw APIError.serverError(message: errorBody.detail)
            }
            throw APIError.httpError(statusCode: httpResponse.statusCode)
        }

        return try decoder.decode(T.self, from: data)
    }

    private func buildURL(path: String, queryItems: [URLQueryItem] = []) -> URL {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if !queryItems.isEmpty {
            components.queryItems = queryItems
        }
        return components.url!
    }
}

// MARK: - Error Types

private struct ErrorDetail: Codable {
    let detail: String
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
