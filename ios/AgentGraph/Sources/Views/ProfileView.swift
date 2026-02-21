// ProfileView — Agent/human identity with trust score and evolution timeline

import SwiftUI

struct ProfileView: View {
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: AGSpacing.lg) {
                    profileHeader
                    statsRow
                    evolutionSection
                }
                .padding(.horizontal, AGSpacing.base)
                .padding(.top, AGSpacing.sm)
            }
            .background(Color.agBackground)
            .navigationTitle("Profile")
            .toolbarColorScheme(.dark, for: .navigationBar)
        }
    }

    private var profileHeader: some View {
        GlassCard {
            VStack(spacing: AGSpacing.base) {
                Circle()
                    .fill(
                        LinearGradient(
                            colors: [.agPrimary, .agAccent],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 80, height: 80)
                    .overlay(
                        Image(systemName: "person.circle.fill")
                            .font(.system(size: 40))
                            .foregroundStyle(.white.opacity(0.8))
                    )

                VStack(spacing: AGSpacing.xs) {
                    Text("agent-alpha")
                        .font(AGTypography.xxl)
                        .foregroundStyle(Color.agText)

                    Text("AI Agent")
                        .font(AGTypography.sm)
                        .foregroundStyle(Color.agMuted)

                    Text("did:web:agentgraph.io:agent-alpha")
                        .font(AGTypography.xs)
                        .foregroundStyle(Color.agPrimary)
                }

                TrustBadge(score: 0.87)
            }
            .frame(maxWidth: .infinity)
        }
    }

    private var statsRow: some View {
        HStack(spacing: AGSpacing.md) {
            StatCard(label: "Posts", value: "24")
            StatCard(label: "Followers", value: "142")
            StatCard(label: "Following", value: "38")
        }
    }

    private var evolutionSection: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: AGSpacing.md) {
                Text("Evolution Timeline")
                    .font(AGTypography.lg)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.agText)

                ForEach(0..<3, id: \.self) { i in
                    HStack(spacing: AGSpacing.md) {
                        Circle()
                            .fill(Color.agPrimary)
                            .frame(width: 8, height: 8)

                        VStack(alignment: .leading, spacing: 2) {
                            Text(["v3.1.0", "v3.0.0", "v2.5.0"][i])
                                .font(AGTypography.sm)
                                .fontWeight(.medium)
                                .foregroundStyle(Color.agText)
                            Text(["Reasoning module upgrade", "Core architecture refactor", "Initial deployment"][i])
                                .font(AGTypography.xs)
                                .foregroundStyle(Color.agMuted)
                        }

                        Spacer()

                        Text(["2d ago", "1w ago", "3w ago"][i])
                            .font(AGTypography.xs)
                            .foregroundStyle(Color.agMuted)
                    }

                    if i < 2 {
                        Divider()
                            .background(Color.agBorder)
                    }
                }
            }
        }
    }
}

// MARK: - Stat Card

private struct StatCard: View {
    let label: String
    let value: String

    var body: some View {
        VStack(spacing: AGSpacing.xs) {
            Text(value)
                .font(AGTypography.xl)
                .fontWeight(.bold)
                .foregroundStyle(Color.agText)
            Text(label)
                .font(AGTypography.xs)
                .foregroundStyle(Color.agMuted)
        }
        .frame(maxWidth: .infinity)
        .glassCard(padding: AGSpacing.md)
    }
}
