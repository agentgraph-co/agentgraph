// BookmarksView — Saved posts with search and sort

import SwiftUI

struct BookmarksView: View {
    @Environment(AuthViewModel.self) private var auth
    @State private var viewModel = BookmarksViewModel()

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            if viewModel.isLoading && viewModel.filteredPosts.isEmpty {
                LoadingStateView(state: .loading)
            } else if viewModel.filteredPosts.isEmpty {
                LoadingStateView(state: .empty(message: "No bookmarks yet. Save posts to find them here."))
            } else {
                ScrollView {
                    VStack(spacing: AGSpacing.sm) {
                        // Sort picker
                        Picker("Sort", selection: Binding(
                            get: { viewModel.sortOrder },
                            set: { viewModel.sortOrder = $0 }
                        )) {
                            ForEach(BookmarksViewModel.SortOrder.allCases, id: \.self) { order in
                                Text(order.rawValue).tag(order)
                            }
                        }
                        .pickerStyle(.segmented)
                        .padding(.horizontal, AGSpacing.sm)

                        ForEach(viewModel.filteredPosts) { post in
                            NavigationLink(value: post.id) {
                                PostCard(
                                    post: post,
                                    onVote: { direction in
                                        // Voting not primary here, but support it
                                    },
                                    onBookmark: {
                                        Task { await viewModel.removeBookmark(postId: post.id) }
                                    }
                                )
                            }
                            .buttonStyle(.plain)
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
                    await viewModel.loadBookmarks()
                }
            }
        }
        .navigationTitle("Bookmarks")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .searchable(
            text: Binding(
                get: { viewModel.searchText },
                set: { viewModel.searchText = $0 }
            ),
            prompt: "Filter bookmarks..."
        )
        .navigationDestination(for: UUID.self) { postId in
            PostDetailView(postId: postId)
        }
        .task {
            await viewModel.loadBookmarks()
        }
    }
}
