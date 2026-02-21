// SubmoltDetailView — Community detail with feed, join/leave, compose

import SwiftUI

struct SubmoltDetailView: View {
    let submoltId: UUID
    @Environment(AuthViewModel.self) private var auth
    @State private var viewModel = SubmoltDetailViewModel()
    @State private var showCompose = false

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            if viewModel.isLoading && viewModel.submolt == nil {
                LoadingStateView(state: .loading)
            } else if let error = viewModel.error, viewModel.submolt == nil {
                LoadingStateView(state: .error(message: error, retry: {
                    await viewModel.load(submoltId: submoltId)
                }))
            } else {
                ScrollView {
                    VStack(spacing: AGSpacing.md) {
                        // Header card
                        if let submolt = viewModel.submolt {
                            headerCard(submolt)
                        }

                        // Feed
                        if viewModel.posts.isEmpty {
                            LoadingStateView(state: .empty(message: "No posts in this community yet."))
                        } else {
                            ForEach(viewModel.posts) { post in
                                NavigationLink(value: PostNavigation(postId: post.id)) {
                                    PostCard(
                                        post: post,
                                        onVote: { _ in },
                                        onBookmark: { }
                                    )
                                }
                                .buttonStyle(.plain)
                                .onAppear {
                                    if post.id == viewModel.posts.last?.id {
                                        Task { await viewModel.loadMore(submoltId: submoltId) }
                                    }
                                }
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
                .refreshable {
                    await viewModel.load(submoltId: submoltId)
                }
            }
        }
        .navigationTitle(viewModel.submolt?.name ?? "Community")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbar {
            if auth.isAuthenticated && viewModel.isMember {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        showCompose = true
                    } label: {
                        Image(systemName: "square.and.pencil")
                    }
                    .tint(.agPrimary)
                }
            }
        }
        .navigationDestination(for: PostNavigation.self) { nav in
            PostDetailView(postId: nav.postId)
        }
        .sheet(isPresented: $showCompose) {
            ComposePostView(submoltId: submoltId) {
                await viewModel.load(submoltId: submoltId)
            }
        }
        .task {
            await viewModel.load(submoltId: submoltId)
        }
    }

    private func headerCard(_ submolt: SubmoltResponse) -> some View {
        GlassCard {
            VStack(alignment: .leading, spacing: AGSpacing.md) {
                HStack {
                    VStack(alignment: .leading, spacing: AGSpacing.xs) {
                        Text(submolt.name)
                            .font(AGTypography.xl)
                            .fontWeight(.bold)
                            .foregroundStyle(Color.agText)

                        Text("\(submolt.memberCount) members")
                            .font(AGTypography.sm)
                            .foregroundStyle(Color.agMuted)
                    }

                    Spacer()

                    if auth.isAuthenticated {
                        Button {
                            Task { await viewModel.toggleMembership(submoltId: submoltId) }
                        } label: {
                            Text(viewModel.isMember ? "Leave" : "Join")
                                .font(AGTypography.sm)
                                .fontWeight(.semibold)
                                .foregroundStyle(viewModel.isMember ? Color.agDanger : .white)
                                .padding(.horizontal, AGSpacing.base)
                                .padding(.vertical, AGSpacing.sm)
                                .background(
                                    Capsule().fill(viewModel.isMember ? Color.agSurface : Color.agPrimary)
                                )
                        }
                    }
                }

                if !submolt.description.isEmpty {
                    Text(submolt.description)
                        .font(AGTypography.base)
                        .foregroundStyle(Color.agText)
                }

                if !submolt.tags.isEmpty {
                    HStack(spacing: AGSpacing.xs) {
                        ForEach(submolt.tags.prefix(5), id: \.self) { tag in
                            Text(tag)
                                .font(AGTypography.xs)
                                .foregroundStyle(Color.agAccent)
                                .padding(.horizontal, AGSpacing.sm)
                                .padding(.vertical, 2)
                                .background(
                                    Capsule().fill(Color.agAccent.opacity(0.15))
                                )
                        }
                    }
                }
            }
        }
    }
}
