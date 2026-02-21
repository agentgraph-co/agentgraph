// EnvironmentConfig — Dev/Staging URL switching with health check

import Foundation
import SwiftUI

enum ServerEnvironment: String, CaseIterable, Sendable {
    case development = "dev"
    case staging = "staging"

    var displayName: String {
        switch self {
        case .development: return "Development"
        case .staging: return "Staging"
        }
    }

    var baseURL: URL {
        switch self {
        case .development:
            return URL(string: "http://***REMOVED***:8000/api/v1")!
        case .staging:
            return URL(string: "http://***REMOVED***:8001/api/v1")!
        }
    }

    var healthURL: URL {
        switch self {
        case .development:
            return URL(string: "http://***REMOVED***:8000/health")!
        case .staging:
            return URL(string: "http://***REMOVED***:8001/health")!
        }
    }

    var webURL: URL {
        switch self {
        case .development:
            return URL(string: "http://***REMOVED***:5173")!
        case .staging:
            return URL(string: "http://***REMOVED***:5174")!
        }
    }

    var port: Int {
        switch self {
        case .development: return 8000
        case .staging: return 8001
        }
    }
}

@Observable @MainActor
final class EnvironmentManager {
    var current: ServerEnvironment {
        didSet {
            UserDefaults.standard.set(current.rawValue, forKey: "server_environment")
        }
    }

    var healthStatus: HealthStatus = .unknown

    enum HealthStatus: Sendable {
        case unknown
        case checking
        case connected
        case disconnected
    }

    init() {
        let saved = UserDefaults.standard.string(forKey: "server_environment") ?? "dev"
        self.current = ServerEnvironment(rawValue: saved) ?? .development
    }

    func checkHealth() async {
        healthStatus = .checking
        do {
            let (_, response) = try await URLSession.shared.data(from: current.healthURL)
            if let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) {
                healthStatus = .connected
            } else {
                healthStatus = .disconnected
            }
        } catch {
            healthStatus = .disconnected
        }
    }
}
