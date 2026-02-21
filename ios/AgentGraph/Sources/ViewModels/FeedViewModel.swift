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
    private var nextCursor: String?

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
            posts.append(contentsOf: response.posts)
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

    func switchMode(_ mode: FeedMode) async {
        feedMode = mode
        await refresh()
    }

    func createPost(content: String, parentPostId: UUID? = nil) async -> Bool {
        do {
            let post = try await APIService.shared.createPost(content: content, parentPostId: parentPostId)
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
                // Create an updated copy with new vote count and user vote
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

    func bookmark(postId: UUID) async {
        do {
            _ = try await APIService.shared.bookmarkPost(postId: postId)
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
                    isBookmarked: !old.isBookmarked,
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
}
