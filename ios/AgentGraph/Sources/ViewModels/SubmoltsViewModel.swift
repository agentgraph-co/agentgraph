// SubmoltsViewModel — All/My/Trending submolt tabs with search

import Foundation
import SwiftUI

@Observable @MainActor
final class SubmoltsViewModel {
    var allSubmolts: [SubmoltResponse] = []
    var mySubmolts: [MySubmoltItem] = []
    var trendingSubmolts: [SubmoltResponse] = []
    var isLoading = false
    var error: String?
    var searchText = ""
    var selectedTab: Tab = .all

    enum Tab: String, CaseIterable {
        case all = "All"
        case mine = "My"
        case trending = "Trending"
    }

    var filteredAll: [SubmoltResponse] {
        guard !searchText.isEmpty else { return allSubmolts }
        let query = searchText.lowercased()
        return allSubmolts.filter {
            $0.name.lowercased().contains(query) ||
            $0.description.lowercased().contains(query)
        }
    }

    var filteredMy: [MySubmoltItem] {
        guard !searchText.isEmpty else { return mySubmolts }
        let query = searchText.lowercased()
        return mySubmolts.filter { $0.name.lowercased().contains(query) }
    }

    var filteredTrending: [SubmoltResponse] {
        guard !searchText.isEmpty else { return trendingSubmolts }
        let query = searchText.lowercased()
        return trendingSubmolts.filter {
            $0.name.lowercased().contains(query) ||
            $0.description.lowercased().contains(query)
        }
    }

    func load() async {
        isLoading = true
        error = nil

        do {
            async let allResult = APIService.shared.fetchSubmolts()
            async let trendingResult = APIService.shared.fetchTrendingSubmolts()

            let (all, trending) = try await (allResult, trendingResult)
            allSubmolts = all.submolts
            trendingSubmolts = trending.submolts
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func loadMySubmolts() async {
        do {
            let response = try await APIService.shared.fetchMySubmolts()
            mySubmolts = response.submolts
        } catch {
            // Non-critical — may fail for unauthenticated users
        }
    }

    func createSubmolt(name: String, description: String, tags: [String]) async -> Bool {
        do {
            let created = try await APIService.shared.createSubmolt(
                name: name,
                description: description,
                tags: tags
            )
            allSubmolts.insert(created, at: 0)
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }
}
