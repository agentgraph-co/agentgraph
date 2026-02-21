// APIServiceTests — URL construction, auth headers, 401 handling

import XCTest
@testable import AgentGraph

// Mock URLProtocol for intercepting network requests
final class MockURLProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = MockURLProtocol.requestHandler else {
            XCTFail("No request handler set")
            return
        }

        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

final class APIServiceTests: XCTestCase {
    private var service: APIService!
    private var session: URLSession!

    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        session = URLSession(configuration: config)
        service = APIService(
            baseURL: URL(string: "http://localhost:8000/api/v1")!,
            session: session
        )
    }

    override func tearDown() {
        MockURLProtocol.requestHandler = nil
        super.tearDown()
    }

    // MARK: - URL Construction

    func testFetchFeedURLPath() async throws {
        var capturedURL: URL?

        MockURLProtocol.requestHandler = { request in
            capturedURL = request.url
            let json = """
            {"posts": [], "next_cursor": null}
            """.data(using: .utf8)!
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200,
                httpVersion: nil, headerFields: nil
            )!
            return (response, json)
        }

        _ = try await service.fetchFeed()

        XCTAssertNotNil(capturedURL)
        XCTAssertTrue(
            capturedURL!.path.contains("/feed/posts"),
            "Feed URL should use /feed/posts not /feed. Got: \(capturedURL!.path)"
        )
    }

    func testFetchFeedIncludesCursorParam() async throws {
        var capturedURL: URL?

        MockURLProtocol.requestHandler = { request in
            capturedURL = request.url
            let json = """
            {"posts": [], "next_cursor": null}
            """.data(using: .utf8)!
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200,
                httpVersion: nil, headerFields: nil
            )!
            return (response, json)
        }

        _ = try await service.fetchFeed(cursor: "test-cursor")

        let components = URLComponents(url: capturedURL!, resolvingAgainstBaseURL: false)!
        let cursorParam = components.queryItems?.first(where: { $0.name == "cursor" })
        XCTAssertEqual(cursorParam?.value, "test-cursor")
    }

    // MARK: - Auth Headers

    func testAuthenticatedRequestIncludesBearerToken() async throws {
        var capturedAuth: String?

        await service.setTokens(access: "test-access-token", refresh: "test-refresh-token")

        MockURLProtocol.requestHandler = { request in
            capturedAuth = request.value(forHTTPHeaderField: "Authorization")
            let json = """
            {
                "id": "11111111-2222-3333-4444-555555555555",
                "type": "human",
                "email": "test@test.com",
                "display_name": "Test",
                "bio_markdown": "",
                "did_web": "did:web:test",
                "is_active": true,
                "is_admin": false,
                "created_at": "2026-01-01T00:00:00"
            }
            """.data(using: .utf8)!
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200,
                httpVersion: nil, headerFields: nil
            )!
            return (response, json)
        }

        _ = try await service.getMe()

        XCTAssertEqual(capturedAuth, "Bearer test-access-token")
    }

    // MARK: - 401 Handling

    func testUnauthorizedWithNoTokenThrows() async {
        await service.clearTokens()

        do {
            _ = try await service.getMe()
            XCTFail("Should have thrown")
        } catch {
            // Expected: unauthorized error
            XCTAssertTrue(error is APIError)
        }
    }

    // MARK: - Error Handling

    func testHttpErrorParsesDetail() async throws {
        MockURLProtocol.requestHandler = { request in
            let json = """
            {"detail": "Post not found"}
            """.data(using: .utf8)!
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 404,
                httpVersion: nil, headerFields: nil
            )!
            return (response, json)
        }

        do {
            _ = try await service.fetchFeed()
            XCTFail("Should have thrown")
        } catch let error as APIError {
            if case .serverError(let message) = error {
                XCTAssertEqual(message, "Post not found")
            } else if case .httpError(let code) = error {
                XCTAssertEqual(code, 404)
            }
        }
    }

    // MARK: - Search URL Construction

    func testSearchURLIncludesQueryParam() async throws {
        var capturedURL: URL?

        MockURLProtocol.requestHandler = { request in
            capturedURL = request.url
            let json = """
            {"entities": [], "posts": [], "entity_count": 0, "post_count": 0}
            """.data(using: .utf8)!
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200,
                httpVersion: nil, headerFields: nil
            )!
            return (response, json)
        }

        _ = try await service.search(query: "test agent")

        let components = URLComponents(url: capturedURL!, resolvingAgainstBaseURL: false)!
        let qParam = components.queryItems?.first(where: { $0.name == "q" })
        XCTAssertEqual(qParam?.value, "test agent")
    }
}
