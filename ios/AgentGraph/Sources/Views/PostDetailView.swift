// PostDetailView — Thread view (post + replies)

import SwiftUI

struct PostDetailView: View {
    let postId: UUID
    @State private var post: PostResponse?
    @State private var replies: [PostResponse] = []
    @State private var isLoading = true
    @State private var error: String?
    @State private var showCompose = false

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            if isLoading {
                LoadingStateView(state: .loading)
            } else if let error {
                LoadingStateView(state: .error(message: error, retry: { await loadPost() }))
            } else if let post {
                ScrollView {
                    LazyVStack(spacing: AGSpacing.base) {
                        // Main post
                        PostCard(post: post) { direction in
                            Task { await vote(postId: post.id, direction: direction) }
                        } onBookmark: {
                            Task { await bookmark(postId: post.id) }
                        }

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
            }
        }
        .navigationTitle("Thread")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    showCompose = true
                } label: {
                    Image(systemName: "arrowshape.turn.up.left")
                }
                .tint(.agPrimary)
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
            _ = try await APIService.shared.voteOnPost(postId: postId, direction: direction)
            await loadPost()
        } catch {}
    }

    private func bookmark(postId: UUID) async {
        do {
            _ = try await APIService.shared.bookmarkPost(postId: postId)
            await loadPost()
        } catch {}
    }
}
