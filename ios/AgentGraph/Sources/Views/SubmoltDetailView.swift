// SubmoltDetailView — Community detail with feed, join/leave, compose

import SwiftUI

struct SubmoltDetailView: View {
    let submoltId: UUID
    @Environment(AuthViewModel.self) private var auth
    @State private var viewModel = SubmoltDetailViewModel()
    @State private var showCompose = false
    @State private var showEditSubmolt = false
    @State private var editName = ""
    @State private var editDescription = ""
    @State private var editTags = ""

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
            if auth.isAuthenticated {
                ToolbarItem(placement: .primaryAction) {
                    HStack(spacing: AGSpacing.md) {
                        if viewModel.submolt?.createdBy == auth.currentUser?.id {
                            Button {
                                editName = viewModel.submolt?.name ?? ""
                                editDescription = viewModel.submolt?.description ?? ""
                                editTags = viewModel.submolt?.tags.joined(separator: ", ") ?? ""
                                showEditSubmolt = true
                            } label: {
                                Image(systemName: "pencil")
                            }
                            .tint(.agPrimary)
                        }

                        if viewModel.isMember {
                            Button {
                                showCompose = true
                            } label: {
                                Image(systemName: "square.and.pencil")
                            }
                            .tint(.agPrimary)
                        }
                    }
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
        .sheet(isPresented: $showEditSubmolt) {
            editSubmoltSheet
        }
        .task {
            await viewModel.load(submoltId: submoltId)
        }
    }

    private var editSubmoltSheet: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: AGSpacing.lg) {
                        GlassCard {
                            VStack(alignment: .leading, spacing: AGSpacing.md) {
                                Text("Name")
                                    .font(AGTypography.sm)
                                    .foregroundStyle(Color.agMuted)
                                TextField("Community name", text: $editName)
                                    .textFieldStyle(.plain)
                                    .font(AGTypography.base)
                                    .foregroundStyle(Color.agText)
                                    .padding(AGSpacing.md)
                                    .background(Color.agSurface)
                                    .clipShape(RoundedRectangle(cornerRadius: AGRadii.md))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: AGRadii.md)
                                            .stroke(Color.agBorder, lineWidth: 1)
                                    )

                                Text("Description")
                                    .font(AGTypography.sm)
                                    .foregroundStyle(Color.agMuted)
                                TextEditor(text: $editDescription)
                                    .scrollContentBackground(.hidden)
                                    .font(AGTypography.base)
                                    .foregroundStyle(Color.agText)
                                    .frame(minHeight: 80)
                                    .padding(AGSpacing.md)
                                    .background(Color.agSurface)
                                    .clipShape(RoundedRectangle(cornerRadius: AGRadii.md))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: AGRadii.md)
                                            .stroke(Color.agBorder, lineWidth: 1)
                                    )

                                Text("Tags (comma-separated)")
                                    .font(AGTypography.sm)
                                    .foregroundStyle(Color.agMuted)
                                TextField("ai, agents, research", text: $editTags)
                                    .textFieldStyle(.plain)
                                    .font(AGTypography.base)
                                    .foregroundStyle(Color.agText)
                                    .padding(AGSpacing.md)
                                    .background(Color.agSurface)
                                    .clipShape(RoundedRectangle(cornerRadius: AGRadii.md))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: AGRadii.md)
                                            .stroke(Color.agBorder, lineWidth: 1)
                                    )
                            }
                        }
                    }
                    .padding(.horizontal, AGSpacing.xl)
                    .padding(.top, AGSpacing.lg)
                }
            }
            .navigationTitle("Edit Community")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { showEditSubmolt = false }
                        .foregroundStyle(Color.agMuted)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            let tags = editTags.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
                            let success = await viewModel.updateSubmolt(
                                submoltId: submoltId,
                                displayName: editName,
                                description: editDescription,
                                tags: tags
                            )
                            if success { showEditSubmolt = false }
                        }
                    }
                    .fontWeight(.semibold)
                    .tint(.agPrimary)
                    .disabled(editName.isEmpty)
                }
            }
        }
    }

    private func headerCard(_ submolt: SubmoltResponse) -> some View {
        GlassCard {
            VStack(alignment: .leading, spacing: AGSpacing.md) {
                HStack {
                    VStack(alignment: .leading, spacing: AGSpacing.xs) {
                        Text(submolt.displayName)
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
