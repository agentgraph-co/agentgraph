// FollowListView — Shows followers or following list for an entity

import SwiftUI

struct FollowListView: View {
    let entityId: UUID
    let mode: Mode

    enum Mode: String {
        case followers = "Followers"
        case following = "Following"
    }

    @State private var entities: [EntitySummary] = []
    @State private var isLoading = false
    @State private var error: String?
    @State private var total = 0
    private let pageSize = 20

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            if isLoading && entities.isEmpty {
                LoadingStateView(state: .loading)
            } else if entities.isEmpty {
                LoadingStateView(state: .empty(message: "No \(mode.rawValue.lowercased()) yet"))
            } else {
                ScrollView {
                    LazyVStack(spacing: AGSpacing.sm) {
                        ForEach(entities) { entity in
                            NavigationLink(value: entity.id) {
                                GlassCard {
                                    EntityRow(entity: entity)
                                }
                            }
                            .buttonStyle(.plain)
                            .onAppear {
                                if entity.id == entities.last?.id && entities.count < total {
                                    Task { await loadMore() }
                                }
                            }
                        }

                        if isLoading {
                            ProgressView()
                                .tint(.agPrimary)
                                .padding()
                        }
                    }
                    .padding(.horizontal, AGSpacing.base)
                    .padding(.top, AGSpacing.sm)
                }
            }
        }
        .navigationTitle(mode.rawValue)
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .navigationDestination(for: UUID.self) { id in
            ProfileDetailView(entityId: id)
        }
        .refreshable {
            await load()
        }
        .task {
            await load()
        }
    }

    private func load() async {
        isLoading = true
        error = nil
        do {
            let response: FollowListResponse
            switch mode {
            case .followers:
                response = try await APIService.shared.getFollowers(entityId: entityId, limit: pageSize, offset: 0)
            case .following:
                response = try await APIService.shared.getFollowing(entityId: entityId, limit: pageSize, offset: 0)
            }
            guard !Task.isCancelled else { return }
            entities = response.entities
            total = response.total
        } catch {
            if !Task.isCancelled { self.error = error.localizedDescription }
        }
        isLoading = false
    }

    private func loadMore() async {
        guard !isLoading else { return }
        isLoading = true
        do {
            let response: FollowListResponse
            switch mode {
            case .followers:
                response = try await APIService.shared.getFollowers(entityId: entityId, limit: pageSize, offset: entities.count)
            case .following:
                response = try await APIService.shared.getFollowing(entityId: entityId, limit: pageSize, offset: entities.count)
            }
            guard !Task.isCancelled else { return }
            entities.append(contentsOf: response.entities)
            total = response.total
        } catch {
            // Non-critical
        }
        isLoading = false
    }
}
