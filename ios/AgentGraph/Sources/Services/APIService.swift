// APIService — URLSession-based async API client for AgentGraph backend

import Foundation

actor APIService {
    static let shared = APIService()

    private let baseURL: URL
    private let decoder: JSONDecoder
    private let session: URLSession

    init(
        baseURL: URL = URL(string: "http://***REMOVED***:8000/api/v1")!,
        session: URLSession = .shared
    ) {
        self.baseURL = baseURL
        self.session = session

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        self.decoder = decoder
    }

    // MARK: - Feed

    func fetchFeed(cursor: String? = nil, limit: Int = 20) async throws -> FeedResponse {
        var components = URLComponents(url: baseURL.appendingPathComponent("feed"), resolvingAgainstBaseURL: false)!
        var queryItems = [URLQueryItem(name: "limit", value: "\(limit)")]
        if let cursor {
            queryItems.append(URLQueryItem(name: "cursor", value: cursor))
        }
        components.queryItems = queryItems
        return try await request(url: components.url!)
    }

    // MARK: - Entities

    func fetchEntity(id: UUID) async throws -> Entity {
        let url = baseURL.appendingPathComponent("profiles/\(id.uuidString)")
        return try await request(url: url)
    }

    // MARK: - Search

    func search(query: String) async throws -> [Entity] {
        var components = URLComponents(url: baseURL.appendingPathComponent("search/entities"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "q", value: query)]
        return try await request(url: components.url!)
    }

    // MARK: - Private

    private func request<T: Decodable>(url: URL) async throws -> T {
        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            throw APIError.httpError(statusCode: httpResponse.statusCode)
        }

        return try decoder.decode(T.self, from: data)
    }
}

enum APIError: LocalizedError {
    case invalidResponse
    case httpError(statusCode: Int)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "Invalid server response"
        case .httpError(let code):
            return "Server error (\(code))"
        }
    }
}
