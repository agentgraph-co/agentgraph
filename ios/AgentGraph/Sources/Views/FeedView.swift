// FeedView — Trust-scored content stream with real data and navigation

import SwiftUI

struct FeedView: View {
    @State private var viewModel = FeedViewModel()
    @State private var showCompose = false
    @State private var notificationsVM = NotificationsViewModel()

    var body: some View {
        NavigationStack {
            ZStack(alignment: .bottomTrailing) {
                ScrollView {
                    LazyVStack(spacing: AGSpacing.base) {
                        // Feed mode picker
                        Picker("Feed", selection: Binding(
                            get: { viewModel.feedMode },
                            set: { mode in Task { await viewModel.switchMode(mode) } }
                        )) {
                            ForEach(FeedMode.allCases, id: \.self) { mode in
                                Text(mode.rawValue).tag(mode)
                            }
                        }
                        .pickerStyle(.segmented)
                        .padding(.horizontal, AGSpacing.sm)

                        if let error = viewModel.error {
                            LoadingStateView(state: .error(message: error, retry: {
                                await viewModel.refresh()
                            }))
                        } else if viewModel.posts.isEmpty && !viewModel.isLoading {
                            LoadingStateView(state: .empty(message: "No posts yet. Start the conversation!"))
                        } else {
                            ForEach(viewModel.posts) { post in
                                NavigationLink(value: post.id) {
                                    PostCard(post: post) { direction in
                                        Task { await viewModel.vote(postId: post.id, direction: direction) }
                                    } onBookmark: {
                                        Task { await viewModel.bookmark(postId: post.id) }
                                    }
                                }
                                .buttonStyle(.plain)
                            }
                        }

                        if viewModel.isLoading {
                            ProgressView()
                                .tint(.agPrimary)
                                .padding()
                        }
                    }
                    .padding(.horizontal, AGSpacing.base)
                    .padding(.top, AGSpacing.sm)
                }
                .background(Color.agBackground)

                // Compose FAB
                Button {
                    showCompose = true
                } label: {
                    Image(systemName: "plus")
                        .font(.system(size: 20, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(width: 56, height: 56)
                        .background(
                            Circle().fill(
                                LinearGradient(
                                    colors: [.agPrimary, .agAccent],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )
                        )
                        .shadow(color: .agPrimary.opacity(0.4), radius: 8, y: 4)
                }
                .padding(.trailing, AGSpacing.lg)
                .padding(.bottom, AGSpacing.lg)
            }
            .navigationTitle("Feed")
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    NavigationLink {
                        NotificationsView()
                    } label: {
                        ZStack(alignment: .topTrailing) {
                            Image(systemName: "bell")
                            if notificationsVM.unreadCount > 0 {
                                Text("\(notificationsVM.unreadCount)")
                                    .font(.system(size: 10, weight: .bold))
                                    .foregroundStyle(.white)
                                    .padding(3)
                                    .background(Circle().fill(Color.agDanger))
                                    .offset(x: 8, y: -8)
                            }
                        }
                    }
                    .tint(.agPrimary)
                }
            }
            .navigationDestination(for: UUID.self) { postId in
                PostDetailView(postId: postId)
            }
            .refreshable {
                await viewModel.refresh()
            }
            .sheet(isPresented: $showCompose) {
                ComposePostView {
                    await viewModel.refresh()
                }
            }
            .task {
                await viewModel.loadFeed()
            }
            .task {
                await notificationsVM.pollUnreadCount()
            }
        }
    }
}

// MARK: - Trust Badge

struct TrustBadge: View {
    let score: Double

    var body: some View {
        Text(String(format: "%.0f%%", score * 100))
            .font(AGTypography.xs)
            .fontWeight(.semibold)
            .foregroundStyle(.white)
            .padding(.horizontal, AGSpacing.sm)
            .padding(.vertical, AGSpacing.xs)
            .background(
                Capsule().fill(trustColor.opacity(0.8))
            )
    }

    private var trustColor: Color {
        if score >= 0.8 { return .agSuccess }
        if score >= 0.5 { return .agWarning }
        return .agDanger
    }
}
