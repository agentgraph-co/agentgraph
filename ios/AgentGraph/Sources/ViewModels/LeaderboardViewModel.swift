// LeaderboardViewModel — Loads ranked entities by metric

import Foundation
import SwiftUI

@Observable @MainActor
final class LeaderboardViewModel {
    var entries: [LeaderboardEntry] = []
    var isLoading = false
    var error: String?
    var metric: Metric = .trust
    var entityFilter: EntityFilter = .all
    var hasMore = true

    private var currentOffset = 0
    private let pageSize = 50

    enum Metric: String, CaseIterable {
        case trust = "Trust"
        case posts = "Posts"
        case followers = "Followers"

        var apiValue: String {
            switch self {
            case .trust: return "trust"
            case .posts: return "posts"
            case .followers: return "followers"
            }
        }
    }

    enum EntityFilter: String, CaseIterable {
        case all = "All"
        case human = "Human"
        case agent = "Agent"

        var apiValue: String? {
            switch self {
            case .all: return nil
            case .human: return "human"
            case .agent: return "agent"
            }
        }
    }

    func loadLeaderboard() async {
        isLoading = true
        error = nil
        currentOffset = 0

        do {
            entries = try await APIService.shared.fetchLeaderboard(
                metric: metric.apiValue,
                entityType: entityFilter.apiValue,
                limit: pageSize,
                offset: 0
            )
            hasMore = entries.count >= pageSize
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func loadMore() async {
        guard hasMore, !isLoading else { return }
        isLoading = true
        currentOffset += pageSize

        do {
            let more = try await APIService.shared.fetchLeaderboard(
                metric: metric.apiValue,
                entityType: entityFilter.apiValue,
                limit: pageSize,
                offset: currentOffset
            )
            entries.append(contentsOf: more)
            hasMore = more.count >= pageSize
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func metricValue(for entry: LeaderboardEntry) -> String {
        switch metric {
        case .trust:
            if let score = entry.trustScore {
                return String(format: "%.0f%%", score * 100)
            }
            return "N/A"
        case .posts:
            return "\(entry.postCount)"
        case .followers:
            return "\(entry.followerCount)"
        }
    }
}
