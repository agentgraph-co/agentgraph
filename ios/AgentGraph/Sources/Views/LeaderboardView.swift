// LeaderboardView — Ranked entity list by trust, posts, or followers

import SwiftUI

struct LeaderboardView: View {
    @State private var viewModel = LeaderboardViewModel()

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            if viewModel.isLoading && viewModel.entries.isEmpty {
                LoadingStateView(state: .loading)
            } else if let error = viewModel.error, viewModel.entries.isEmpty {
                LoadingStateView(state: .error(message: error, retry: {
                    await viewModel.loadLeaderboard()
                }))
            } else if viewModel.entries.isEmpty {
                LoadingStateView(state: .empty(message: "No leaderboard data available."))
            } else {
                ScrollView {
                    VStack(spacing: AGSpacing.sm) {
                        // Metric picker
                        Picker("Metric", selection: Binding(
                            get: { viewModel.metric },
                            set: { newValue in
                                viewModel.metric = newValue
                                Task { await viewModel.loadLeaderboard() }
                            }
                        )) {
                            ForEach(LeaderboardViewModel.Metric.allCases, id: \.self) { m in
                                Text(m.rawValue).tag(m)
                            }
                        }
                        .pickerStyle(.segmented)
                        .padding(.horizontal, AGSpacing.sm)

                        // Entity type filter
                        Picker("Type", selection: Binding(
                            get: { viewModel.entityFilter },
                            set: { newValue in
                                viewModel.entityFilter = newValue
                                Task { await viewModel.loadLeaderboard() }
                            }
                        )) {
                            ForEach(LeaderboardViewModel.EntityFilter.allCases, id: \.self) { f in
                                Text(f.rawValue).tag(f)
                            }
                        }
                        .pickerStyle(.segmented)
                        .padding(.horizontal, AGSpacing.sm)

                        // Leaderboard entries
                        ForEach(Array(viewModel.entries.enumerated()), id: \.element.id) { index, entry in
                            NavigationLink(value: entry.id) {
                                leaderboardCard(rank: index + 1, entry: entry)
                            }
                            .buttonStyle(.plain)
                            .onAppear {
                                if index == viewModel.entries.count - 1 {
                                    Task { await viewModel.loadMore() }
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
                    await viewModel.loadLeaderboard()
                }
            }
        }
        .navigationTitle("Leaderboard")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .navigationDestination(for: UUID.self) { entityId in
            ProfileDetailView(entityId: entityId)
        }
        .task {
            await viewModel.loadLeaderboard()
        }
    }

    private func leaderboardCard(rank: Int, entry: LeaderboardEntry) -> some View {
        GlassCard {
            HStack(spacing: AGSpacing.md) {
                // Rank badge
                Text("\(rank)")
                    .font(AGTypography.lg)
                    .fontWeight(.bold)
                    .foregroundStyle(rank <= 3 ? Color.agAccent : Color.agMuted)
                    .frame(width: 32)

                // Avatar
                Circle()
                    .fill(
                        LinearGradient(
                            colors: [.agPrimary, .agAccent],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 40, height: 40)
                    .overlay(
                        Text(String(entry.displayName.prefix(1)).uppercased())
                            .font(AGTypography.base)
                            .fontWeight(.bold)
                            .foregroundStyle(.white)
                    )

                // Name + type
                VStack(alignment: .leading, spacing: 2) {
                    Text(entry.displayName)
                        .font(AGTypography.base)
                        .fontWeight(.medium)
                        .foregroundStyle(Color.agText)
                        .lineLimit(1)
                    Text(entry.type == "agent" ? "AI Agent" : "Human")
                        .font(AGTypography.xs)
                        .foregroundStyle(Color.agMuted)
                }

                Spacer()

                // Metric value
                Text(viewModel.metricValue(for: entry))
                    .font(AGTypography.lg)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.agPrimary)
            }
        }
    }
}
