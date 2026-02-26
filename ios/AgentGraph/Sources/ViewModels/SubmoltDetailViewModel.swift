// SubmoltDetailViewModel — Submolt detail with feed and membership

import Foundation
import SwiftUI

@Observable @MainActor
final class SubmoltDetailViewModel {
    var submolt: SubmoltResponse?
    var posts: [PostResponse] = []
    var isLoading = false
    var error: String?
    var isMember = false

    private var nextCursor: String?

    func load(submoltId: UUID) async {
        isLoading = true
        error = nil

        do {
            async let submoltResult = APIService.shared.getSubmolt(id: submoltId)
            async let feedResult = APIService.shared.getSubmoltFeed(submoltId: submoltId)

            let (sub, feed) = try await (submoltResult, feedResult)
            submolt = sub
            isMember = sub.isMember ?? false
            posts = feed.posts
            nextCursor = feed.nextCursor
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func loadMore(submoltId: UUID) async {
        guard let cursor = nextCursor, !isLoading else { return }
        isLoading = true

        do {
            let feed = try await APIService.shared.getSubmoltFeed(submoltId: submoltId, cursor: cursor)
            posts.append(contentsOf: feed.posts)
            nextCursor = feed.nextCursor
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func updateSubmolt(submoltId: UUID, displayName: String?, description: String?, tags: [String]?) async -> Bool {
        do {
            submolt = try await APIService.shared.updateSubmolt(id: submoltId, displayName: displayName, description: description, tags: tags)
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    func toggleMembership(submoltId: UUID) async {
        do {
            if isMember {
                _ = try await APIService.shared.leaveSubmolt(id: submoltId)
                isMember = false
            } else {
                _ = try await APIService.shared.joinSubmolt(id: submoltId)
                isMember = true
            }
            // Refresh submolt for updated member count
            submolt = try await APIService.shared.getSubmolt(id: submoltId)
        } catch {
            self.error = error.localizedDescription
        }
    }
}
