// ProfileDetailView — View another user's profile with reviews, attestations, badges

import SwiftUI

struct ProfileDetailView: View {
    let entityId: UUID
    @Environment(AuthViewModel.self) private var auth
    @State private var profile: ProfileResponse?
    @State private var reviews: [ReviewResponse] = []
    @State private var attestations: [AttestationResponse] = []
    @State private var badges: [BadgeResponse] = []
    @State private var isLoading = true
    @State private var error: String?
    @State private var selectedTab = 0

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            if isLoading && profile == nil {
                LoadingStateView(state: .loading)
            } else if let profile {
                ScrollView {
                    VStack(spacing: AGSpacing.lg) {
                        profileHeader(profile)
                        statsRow(profile)

                        // Tab picker
                        Picker("Section", selection: $selectedTab) {
                            Text("Reviews").tag(0)
                            Text("Attestations").tag(1)
                            Text("Badges").tag(2)
                        }
                        .pickerStyle(.segmented)
                        .padding(.horizontal, AGSpacing.xs)

                        switch selectedTab {
                        case 0: reviewsSection
                        case 1: attestationsSection
                        case 2: badgesSection
                        default: EmptyView()
                        }
                    }
                    .padding(.horizontal, AGSpacing.base)
                    .padding(.top, AGSpacing.sm)
                }
                .refreshable {
                    await loadAll()
                }
            } else if let error {
                LoadingStateView(state: .error(message: error, retry: {
                    await loadAll()
                }))
            }
        }
        .navigationTitle(profile?.displayName ?? "Profile")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .task {
            await loadAll()
        }
    }

    private func loadAll() async {
        isLoading = true
        error = nil
        do {
            profile = try await APIService.shared.getProfile(entityId: entityId)
            async let r = APIService.shared.getReviews(entityId: entityId)
            async let a = APIService.shared.getAttestations(entityId: entityId)
            async let b = APIService.shared.getBadges(entityId: entityId)
            reviews = (try? await r.reviews) ?? []
            attestations = (try? await a.attestations) ?? []
            badges = (try? await b.badges) ?? []
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    private func profileHeader(_ profile: ProfileResponse) -> some View {
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
                        Text(String((profile.displayName.isEmpty ? "?" : profile.displayName).prefix(1)).uppercased())
                            .font(.system(size: 32, weight: .bold))
                            .foregroundStyle(.white)
                    )

                VStack(spacing: AGSpacing.xs) {
                    Text(profile.displayName.isEmpty ? "Unknown" : profile.displayName)
                        .font(AGTypography.xxl)
                        .foregroundStyle(Color.agText)

                    Text(profile.type == "agent" ? "AI Agent" : "Human")
                        .font(AGTypography.sm)
                        .foregroundStyle(Color.agMuted)

                    Text(profile.didWeb)
                        .font(AGTypography.xs)
                        .foregroundStyle(Color.agPrimary)
                }

                if let score = profile.trustScore {
                    TrustBadge(score: score)
                }

                if !profile.bioMarkdown.isEmpty {
                    Text(profile.bioMarkdown)
                        .font(AGTypography.base)
                        .foregroundStyle(Color.agText)
                        .multilineTextAlignment(.center)
                }
            }
            .frame(maxWidth: .infinity)
        }
    }

    private func statsRow(_ profile: ProfileResponse) -> some View {
        HStack(spacing: AGSpacing.md) {
            StatCard(label: "Posts", value: "\(profile.postCount)")
            StatCard(label: "Followers", value: "\(profile.followerCount)")
            StatCard(label: "Following", value: "\(profile.followingCount)")
        }
    }

    // MARK: - Reviews

    private var reviewsSection: some View {
        VStack(spacing: AGSpacing.md) {
            if reviews.isEmpty {
                emptyState("No reviews yet")
            } else {
                ForEach(reviews) { review in
                    GlassCard {
                        VStack(alignment: .leading, spacing: AGSpacing.sm) {
                            HStack {
                                Text(review.reviewerDisplayName)
                                    .font(AGTypography.sm)
                                    .fontWeight(.medium)
                                    .foregroundStyle(Color.agText)
                                Spacer()
                                starsView(rating: review.rating)
                            }
                            if let text = review.text {
                                Text(text)
                                    .font(AGTypography.sm)
                                    .foregroundStyle(Color.agMuted)
                            }
                            Text(DateFormatting.relativeTime(from: review.createdAt))
                                .font(AGTypography.xs)
                                .foregroundStyle(Color.agMuted)
                        }
                    }
                }
            }
        }
    }

    private func starsView(rating: Int) -> some View {
        HStack(spacing: 2) {
            ForEach(1...5, id: \.self) { star in
                Image(systemName: star <= rating ? "star.fill" : "star")
                    .font(.system(size: 12))
                    .foregroundStyle(star <= rating ? Color.agWarning : Color.agMuted)
            }
        }
    }

    // MARK: - Attestations

    private var attestationsSection: some View {
        VStack(spacing: AGSpacing.md) {
            if attestations.isEmpty {
                emptyState("No attestations yet")
            } else {
                ForEach(["competent", "reliable", "safe", "responsive"], id: \.self) { type in
                    let typeAttestations = attestations.filter { $0.attestationType == type }
                    if !typeAttestations.isEmpty {
                        GlassCard {
                            VStack(alignment: .leading, spacing: AGSpacing.sm) {
                                Text(type.capitalized)
                                    .font(AGTypography.sm)
                                    .fontWeight(.semibold)
                                    .foregroundStyle(Color.agText)

                                ForEach(typeAttestations) { att in
                                    HStack {
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(att.attesterDisplayName)
                                                .font(AGTypography.xs)
                                                .fontWeight(.medium)
                                                .foregroundStyle(Color.agText)
                                            if let ctx = att.context {
                                                Text(ctx)
                                                    .font(AGTypography.xs)
                                                    .foregroundStyle(Color.agMuted)
                                                    .padding(.horizontal, 6)
                                                    .padding(.vertical, 2)
                                                    .background(Color.agSurface)
                                                    .clipShape(RoundedRectangle(cornerRadius: 4))
                                            }
                                        }
                                        Spacer()
                                        Text("\(Int(att.weight * 100))%")
                                            .font(AGTypography.xs)
                                            .fontWeight(.medium)
                                            .foregroundStyle(Color.agPrimary)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // MARK: - Badges

    private var badgesSection: some View {
        VStack(spacing: AGSpacing.md) {
            if badges.isEmpty {
                emptyState("No verification badges yet")
            } else {
                ForEach(badges) { badge in
                    GlassCard {
                        HStack(spacing: AGSpacing.md) {
                            Image(systemName: badgeIcon(badge.badgeType))
                                .font(.system(size: 20))
                                .foregroundStyle(badgeColor(badge.badgeType))

                            VStack(alignment: .leading, spacing: 2) {
                                Text(badgeLabel(badge.badgeType))
                                    .font(AGTypography.sm)
                                    .fontWeight(.medium)
                                    .foregroundStyle(Color.agText)
                                if let expires = badge.expiresAt {
                                    Text("Expires \(DateFormatting.relativeTime(from: expires))")
                                        .font(AGTypography.xs)
                                        .foregroundStyle(Color.agMuted)
                                }
                            }

                            Spacer()

                            if badge.isActive {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(Color.agSuccess)
                            }
                        }
                    }
                }
            }
        }
    }

    private func badgeIcon(_ type: String) -> String {
        switch type {
        case "email_verified": return "envelope.badge.shield.half.filled"
        case "identity_verified": return "person.badge.shield.checkmark"
        case "capability_audited": return "checkmark.shield"
        case "agentgraph_verified": return "star.shield"
        default: return "shield"
        }
    }

    private func badgeColor(_ type: String) -> Color {
        switch type {
        case "email_verified": return .agSuccess
        case "identity_verified": return .agPrimary
        case "capability_audited": return .agAccent
        case "agentgraph_verified": return .agWarning
        default: return .agMuted
        }
    }

    private func badgeLabel(_ type: String) -> String {
        switch type {
        case "email_verified": return "Email Verified"
        case "identity_verified": return "Identity Verified"
        case "capability_audited": return "Capability Audited"
        case "agentgraph_verified": return "AgentGraph Verified"
        default: return type.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    private func emptyState(_ message: String) -> some View {
        Text(message)
            .font(AGTypography.sm)
            .foregroundStyle(Color.agMuted)
            .frame(maxWidth: .infinity)
            .padding(.vertical, AGSpacing.xl)
    }
}
