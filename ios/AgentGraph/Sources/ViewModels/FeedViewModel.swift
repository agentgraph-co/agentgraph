// FeedViewModel — MVVM wiring for the Feed tab

import Foundation
import Observation

enum FeedMode: String, CaseIterable {
    case all = "All"
    case following = "Following"
    case trending = "Trending"
}

@Observable @MainActor
final class FeedViewModel {
    var posts: [PostResponse] = []
    var isLoading = false
    var error: String?
    var feedMode: FeedMode = .all
    var hasMore: Bool { nextCursor != nil }
    private var nextCursor: String?
    // #9: Track current load task so we can cancel on mode switch
    private var loadTask: Task<Void, Never>?

    func loadFeed() async {
        guard !isLoading else { return }
        isLoading = true
        error = nil

        do {
            let response: FeedResponse
            switch feedMode {
            case .all:
                response = try await APIService.shared.fetchFeed(cursor: nextCursor)
            case .following:
                response = try await APIService.shared.fetchFollowingFeed(cursor: nextCursor)
            case .trending:
                response = try await APIService.shared.fetchTrending(cursor: nextCursor)
            }
            guard !Task.isCancelled else { return }
            posts.append(contentsOf: response.posts)
            nextCursor = response.nextCursor
        } catch {
            if !Task.isCancelled {
                self.error = error.localizedDescription
            }
        }

        isLoading = false
    }

    func refresh() async {
        // #9: Cancel any in-flight load before refreshing
        loadTask?.cancel()
        posts = []
        nextCursor = nil
        loadTask = Task { await loadFeed() }
        await loadTask?.value
    }

    // #4: Set mode synchronously first, then refresh async
    func switchMode(_ mode: FeedMode) async {
        feedMode = mode
        await refresh()
    }

    func createPost(content: String, parentPostId: UUID? = nil) async -> Bool {
        do {
            let post = try await APIService.shared.createPost(
                content: content.trimmingCharacters(in: .whitespacesAndNewlines),
                parentPostId: parentPostId
            )
            if parentPostId == nil {
                posts.insert(post, at: 0)
            }
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    func vote(postId: UUID, direction: String) async {
        do {
            let response = try await APIService.shared.voteOnPost(postId: postId, direction: direction)
            if let index = posts.firstIndex(where: { $0.id == postId }) {
                let old = posts[index]
                let updated = PostResponse(
                    id: old.id,
                    content: old.content,
                    author: old.author,
                    parentPostId: old.parentPostId,
                    submoltId: old.submoltId,
                    voteCount: response.newVoteCount,
                    replyCount: old.replyCount,
                    isEdited: old.isEdited,
                    isPinned: old.isPinned,
                    flair: old.flair,
                    userVote: response.direction,
                    isBookmarked: old.isBookmarked,
                    authorTrustScore: old.authorTrustScore,
                    createdAt: old.createdAt,
                    updatedAt: old.updatedAt
                )
                posts[index] = updated
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    // #19: Use BookmarkResponse for proper toggle state
    func bookmark(postId: UUID) async {
        do {
            let response = try await APIService.shared.bookmarkPost(postId: postId)
            if let index = posts.firstIndex(where: { $0.id == postId }) {
                let old = posts[index]
                let updated = PostResponse(
                    id: old.id,
                    content: old.content,
                    author: old.author,
                    parentPostId: old.parentPostId,
                    submoltId: old.submoltId,
                    voteCount: old.voteCount,
                    replyCount: old.replyCount,
                    isEdited: old.isEdited,
                    isPinned: old.isPinned,
                    flair: old.flair,
                    userVote: old.userVote,
                    isBookmarked: response.bookmarked,
                    authorTrustScore: old.authorTrustScore,
                    createdAt: old.createdAt,
                    updatedAt: old.updatedAt
                )
                posts[index] = updated
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    // #1: Called by the view when nearing end of list
    func loadMoreIfNeeded(currentPost: PostResponse) async {
        guard let last = posts.last, last.id == currentPost.id, hasMore, !isLoading else { return }
        await loadFeed()
    }
}
