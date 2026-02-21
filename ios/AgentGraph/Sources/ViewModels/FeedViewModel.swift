// FeedViewModel — MVVM wiring for the Feed tab

import Foundation
import Observation

@Observable @MainActor
final class FeedViewModel {
    var posts: [Post] = []
    var isLoading = false
    var error: String?
    private var nextCursor: String?

    func loadFeed() async {
        guard !isLoading else { return }
        isLoading = true
        error = nil

        do {
            let response = try await APIService.shared.fetchFeed(cursor: nextCursor)
            posts.append(contentsOf: response.items)
            nextCursor = response.nextCursor
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func refresh() async {
        posts = []
        nextCursor = nil
        await loadFeed()
    }
}
