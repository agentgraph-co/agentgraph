// BookmarksViewModel — Loads and manages bookmarked posts

import Foundation
import SwiftUI

@Observable @MainActor
final class BookmarksViewModel {
    var posts: [PostResponse] = []
    var isLoading = false
    var error: String?
    var searchText = ""
    var sortOrder: SortOrder = .newest

    enum SortOrder: String, CaseIterable {
        case newest = "Newest"
        case oldest = "Oldest"
        case mostVotes = "Most Votes"
    }

    private var nextCursor: String?
    private var allPosts: [PostResponse] = []

    var filteredPosts: [PostResponse] {
        var result = allPosts

        if !searchText.isEmpty {
            let query = searchText.lowercased()
            result = result.filter {
                $0.content.lowercased().contains(query) ||
                $0.author.displayName.lowercased().contains(query)
            }
        }

        switch sortOrder {
        case .newest:
            result.sort { $0.createdAt > $1.createdAt }
        case .oldest:
            result.sort { $0.createdAt < $1.createdAt }
        case .mostVotes:
            result.sort { $0.voteCount > $1.voteCount }
        }

        return result
    }

    func loadBookmarks() async {
        guard !isLoading else { return }
        isLoading = true
        error = nil

        do {
            let response = try await APIService.shared.fetchBookmarks()
            allPosts = response.posts
            nextCursor = response.nextCursor
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func loadMore() async {
        guard let cursor = nextCursor, !isLoading else { return }
        isLoading = true

        do {
            let response = try await APIService.shared.fetchBookmarks(cursor: cursor)
            allPosts.append(contentsOf: response.posts)
            nextCursor = response.nextCursor
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func removeBookmark(postId: UUID) async {
        do {
            _ = try await APIService.shared.bookmarkPost(postId: postId)
            allPosts.removeAll { $0.id == postId }
        } catch {
            self.error = error.localizedDescription
        }
    }
}
