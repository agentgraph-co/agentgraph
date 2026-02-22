// AnalyticsService — Fire-and-forget analytics event tracking

import Foundation

actor AnalyticsService {
    static let shared = AnalyticsService()

    private let sessionId: String
    private let encoder = JSONEncoder()

    private init() {
        if let existing = UserDefaults.standard.string(forKey: "ag_session_id") {
            self.sessionId = existing
        } else {
            let newId = UUID().uuidString
            UserDefaults.standard.set(newId, forKey: "ag_session_id")
            self.sessionId = newId
        }
    }

    nonisolated func trackEvent(
        type: String,
        page: String,
        intent: String? = nil,
        metadata: [String: String]? = nil
    ) {
        Task.detached { [sessionId, encoder] in
            do {
                let saved = UserDefaults.standard.string(forKey: "server_environment") ?? "dev"
                let environment = ServerEnvironment(rawValue: saved) ?? .development
                let baseURL = environment.baseURL
                let url = baseURL.appendingPathComponent("analytics/event")

                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.timeoutInterval = 5

                let body: [String: Any?] = [
                    "event_type": type,
                    "session_id": sessionId,
                    "page": page,
                    "intent": intent,
                    "metadata": metadata,
                ]
                let filtered = body.compactMapValues { $0 }
                request.httpBody = try JSONSerialization.data(withJSONObject: filtered)

                _ = try await URLSession.shared.data(for: request)
            } catch {
                // Silent failure — analytics should never block the user
            }
        }
    }
}
