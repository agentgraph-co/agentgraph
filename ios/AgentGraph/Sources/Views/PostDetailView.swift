// PostDetailView — Thread view (post + replies) with pull-to-refresh

import SwiftUI

struct PostDetailView: View {
    let postId: UUID
    @Environment(AuthViewModel.self) private var auth
    @State private var post: PostResponse?
    @State private var replies: [PostResponse] = []
    @State private var isLoading = true
    @State private var error: String?
    @State private var showCompose = false
    @State private var showLoginPrompt = false
    @State private var showReport = false
    @State private var showEdit = false

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            if isLoading && post == nil {
                LoadingStateView(state: .loading)
            } else if let error, post == nil {
                LoadingStateView(state: .error(message: error, retry: { await loadPost() }))
            } else if let post {
                ScrollView {
                    LazyVStack(spacing: AGSpacing.base) {
                        // Main post (no line limit in detail view)
                        PostCard(
                            post: post,
                            lineLimit: nil,
                            onVote: auth.isAuthenticated ? { direction in
                                Task { await vote(postId: post.id, direction: direction) }
                            } : { _ in showLoginPrompt = true },
                            onBookmark: auth.isAuthenticated ? {
                                Task { await bookmark(postId: post.id) }
                            } : { showLoginPrompt = true }
                        )

                        // Reply count header
                        if !replies.isEmpty {
                            HStack {
                                Text("\(replies.count) Replies")
                                    .font(AGTypography.lg)
                                    .fontWeight(.semibold)
                                    .foregroundStyle(Color.agText)
                                Spacer()
                            }
                            .padding(.top, AGSpacing.sm)
                        }

                        // Replies
                        ForEach(replies) { reply in
                            NavigationLink(value: reply.id) {
                                PostCard(post: reply)
                            }
                            .buttonStyle(.plain)
                        }

                        if replies.isEmpty && !isLoading {
                            LoadingStateView(state: .empty(message: "No replies yet. Be the first to respond!"))
                        }
                    }
                    .padding(.horizontal, AGSpacing.base)
                    .padding(.top, AGSpacing.sm)
                }
                // #18: Pull-to-refresh
                .refreshable {
                    await loadPost()
                }
            }
        }
        .navigationTitle("Thread")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbar {
            // #2: Gate reply behind auth
            if auth.isAuthenticated {
                ToolbarItem(placement: .primaryAction) {
                    HStack(spacing: AGSpacing.md) {
                        Button {
                            showCompose = true
                        } label: {
                            Image(systemName: "arrowshape.turn.up.left")
                        }
                        .tint(.agPrimary)

                        Menu {
                            if post?.author.id == auth.currentUser?.id {
                                Button {
                                    showEdit = true
                                } label: {
                                    Label("Edit", systemImage: "pencil")
                                }
                            }
                            Button {
                                showReport = true
                            } label: {
                                Label("Report", systemImage: "flag")
                            }
                        } label: {
                            Image(systemName: "ellipsis.circle")
                        }
                        .tint(.agPrimary)
                    }
                }
            }
        }
        .navigationDestination(for: UUID.self) { replyId in
            PostDetailView(postId: replyId)
        }
        .sheet(isPresented: $showCompose) {
            ComposePostView(parentPostId: postId) {
                await loadReplies()
            }
        }
        .sheet(isPresented: $showReport) {
            ReportContentView(targetType: "post", targetId: postId)
        }
        .sheet(isPresented: $showEdit) {
            if let post {
                EditPostView(postId: post.id, currentContent: post.content) { updatedPost in
                    self.post = updatedPost
                }
            }
        }
        .alert("Sign In Required", isPresented: $showLoginPrompt) {
            Button("Sign In") {
                auth.exitGuestMode()
            }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("Sign in to vote, reply, and bookmark.")
        }
        .task {
            await loadPost()
        }
    }

    private func loadPost() async {
        isLoading = true
        error = nil
        do {
            post = try await APIService.shared.getPost(id: postId)
            await loadReplies()
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    private func loadReplies() async {
        do {
            let response = try await APIService.shared.getReplies(postId: postId)
            replies = response.posts
        } catch {
            // Non-critical failure
        }
    }

    private func vote(postId: UUID, direction: String) async {
        do {
            let response = try await APIService.shared.voteOnPost(postId: postId, direction: direction)
            // Update local state instead of reloading
            if let currentPost = post, currentPost.id == postId {
                post = PostResponse(
                    id: currentPost.id, content: currentPost.content, author: currentPost.author,
                    parentPostId: currentPost.parentPostId, submoltId: currentPost.submoltId,
                    voteCount: response.newVoteCount, replyCount: currentPost.replyCount,
                    isEdited: currentPost.isEdited, isPinned: currentPost.isPinned,
                    flair: currentPost.flair, userVote: response.direction,
                    isBookmarked: currentPost.isBookmarked, authorTrustScore: currentPost.authorTrustScore,
                    createdAt: currentPost.createdAt, updatedAt: currentPost.updatedAt
                )
            }
        } catch {
            // Silently handle
        }
    }

    private func bookmark(postId: UUID) async {
        do {
            let response = try await APIService.shared.bookmarkPost(postId: postId)
            if let currentPost = post, currentPost.id == postId {
                post = PostResponse(
                    id: currentPost.id, content: currentPost.content, author: currentPost.author,
                    parentPostId: currentPost.parentPostId, submoltId: currentPost.submoltId,
                    voteCount: currentPost.voteCount, replyCount: currentPost.replyCount,
                    isEdited: currentPost.isEdited, isPinned: currentPost.isPinned,
                    flair: currentPost.flair, userVote: currentPost.userVote,
                    isBookmarked: response.bookmarked, authorTrustScore: currentPost.authorTrustScore,
                    createdAt: currentPost.createdAt, updatedAt: currentPost.updatedAt
                )
            }
        } catch {
            // Silently handle
        }
    }
}
