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
    private var isWebSocketSubscribed = false

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

    // MARK: - WebSocket Live Updates

    func subscribeToLiveUpdates() async {
        guard !isWebSocketSubscribed else { return }
        isWebSocketSubscribed = true

        await WebSocketService.shared.subscribe(channel: "feed") { [weak self] data in
            Task { @MainActor [weak self] in
                self?.handleFeedEvent(data)
            }
        }
    }

    private func handleFeedEvent(_ data: Data) {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = json["type"] as? String else { return }

        switch type {
        case "new_post":
            handleNewPost(json)
        case "vote_update":
            handleVoteUpdate(json)
        default:
            break
        }
    }

    private func handleNewPost(_ json: [String: Any]) {
        guard let postDict = json["post"] as? [String: Any],
              let idString = postDict["id"] as? String,
              let id = UUID(uuidString: idString),
              let content = postDict["content"] as? String,
              let authorId = postDict["author_id"] as? String,
              let authorName = postDict["author_display_name"] as? String else { return }

        // Don't insert duplicates
        guard !posts.contains(where: { $0.id == id }) else { return }

        // Only prepend for "all" mode
        guard feedMode == .all else { return }

        let author = PostAuthor(
            id: UUID(uuidString: authorId) ?? UUID(),
            displayName: authorName,
            type: "human",
            didWeb: "",
            autonomyLevel: nil,
            avatarUrl: nil
        )

        let post = PostResponse(
            id: id,
            content: content,
            author: author,
            parentPostId: nil,
            submoltId: nil,
            voteCount: 0,
            replyCount: 0,
            isEdited: false,
            isPinned: false,
            flair: nil,
            userVote: nil,
            isBookmarked: false,
            authorTrustScore: nil,
            createdAt: Date(),
            updatedAt: Date()
        )

        posts.insert(post, at: 0)
    }

    private func handleVoteUpdate(_ json: [String: Any]) {
        guard let postIdString = json["post_id"] as? String,
              let postId = UUID(uuidString: postIdString),
              let voteCount = json["vote_count"] as? Int else { return }

        if let index = posts.firstIndex(where: { $0.id == postId }) {
            let old = posts[index]
            posts[index] = PostResponse(
                id: old.id,
                content: old.content,
                author: old.author,
                parentPostId: old.parentPostId,
                submoltId: old.submoltId,
                voteCount: voteCount,
                replyCount: old.replyCount,
                isEdited: old.isEdited,
                isPinned: old.isPinned,
                flair: old.flair,
                userVote: old.userVote,
                isBookmarked: old.isBookmarked,
                authorTrustScore: old.authorTrustScore,
                createdAt: old.createdAt,
                updatedAt: old.updatedAt
            )
        }
    }
}
