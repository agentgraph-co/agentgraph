// EnvironmentConfig — Dev/Staging/Production URL switching with health check

import Foundation
import SwiftUI

enum ServerEnvironment: String, CaseIterable, Sendable {
    case development = "dev"
    case staging = "staging"
    case production = "prod"

    var displayName: String {
        switch self {
        case .development: return "Development"
        case .staging: return "Staging"
        case .production: return "Production"
        }
    }

    var baseURL: URL {
        switch self {
        case .development:
            return URL(string: "http://***REMOVED***:8000/api/v1")!
        case .staging:
            return URL(string: "http://***REMOVED***:8001/api/v1")!
        case .production:
            return URL(string: "https://api.agentgraph.io/api/v1")!
        }
    }

    var healthURL: URL {
        switch self {
        case .development:
            return URL(string: "http://***REMOVED***:8000/health")!
        case .staging:
            return URL(string: "http://***REMOVED***:8001/health")!
        case .production:
            return URL(string: "https://api.agentgraph.io/health")!
        }
    }

    var webURL: URL {
        switch self {
        case .development:
            return URL(string: "http://***REMOVED***:5173")!
        case .staging:
            return URL(string: "http://***REMOVED***:5174")!
        case .production:
            return URL(string: "https://agentgraph.io")!
        }
    }

    var wsURL: URL {
        switch self {
        case .development:
            return URL(string: "ws://***REMOVED***:8000/api/v1/ws")!
        case .staging:
            return URL(string: "ws://***REMOVED***:8001/api/v1/ws")!
        case .production:
            return URL(string: "wss://api.agentgraph.io/api/v1/ws")!
        }
    }

    var port: Int {
        switch self {
        case .development: return 8000
        case .staging: return 8001
        case .production: return 443
        }
    }

    /// Environments shown in the picker UI — production is excluded in debug builds
    static var selectableCases: [ServerEnvironment] {
        #if DEBUG
        return allCases
        #else
        return [.production]
        #endif
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
        #if DEBUG
        let saved = UserDefaults.standard.string(forKey: "server_environment") ?? "dev"
        self.current = ServerEnvironment(rawValue: saved) ?? .development
        #else
        self.current = .production
        #endif
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
