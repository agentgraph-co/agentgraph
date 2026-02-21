// ProfileView — Real profile data, staging CTA, settings, edit mode

import SwiftUI

struct ProfileView: View {
    @Environment(AuthViewModel.self) private var auth
    @Environment(EnvironmentManager.self) private var envManager
    @State private var viewModel = ProfileViewModel()
    @State private var showEditSheet = false
    @State private var editDisplayName = ""
    @State private var editBio = ""

    var body: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                if !auth.isAuthenticated {
                    // Guest mode — prompt to sign in
                    guestProfilePrompt
                } else if viewModel.isLoading && viewModel.profile == nil {
                    LoadingStateView(state: .loading)
                } else if let profile = viewModel.profile {
                    ScrollView {
                        VStack(spacing: AGSpacing.lg) {
                            profileHeader(profile)
                            statsRow(profile)

                            // Evolution timeline
                            if !viewModel.evolutionRecords.isEmpty {
                                evolutionSection
                            }

                            // Bookmarks (own profile only)
                            if profile.isOwnProfile {
                                NavigationLink {
                                    BookmarksView()
                                } label: {
                                    GlassCard {
                                        HStack(spacing: AGSpacing.md) {
                                            Image(systemName: "bookmark.fill")
                                                .foregroundStyle(Color.agPrimary)
                                            Text("Bookmarks")
                                                .font(AGTypography.base)
                                                .fontWeight(.medium)
                                                .foregroundStyle(Color.agText)
                                            Spacer()
                                            Image(systemName: "chevron.right")
                                                .font(AGTypography.xs)
                                                .foregroundStyle(Color.agMuted)
                                        }
                                    }
                                }
                                .buttonStyle(.plain)
                            }

                            // Staging CTA (own profile only)
                            if profile.isOwnProfile {
                                stagingCTA
                            }
                        }
                        .padding(.horizontal, AGSpacing.base)
                        .padding(.top, AGSpacing.sm)
                    }
                    // #18: Pull-to-refresh
                    .refreshable {
                        if let id = auth.currentUser?.id {
                            await viewModel.loadProfile(entityId: id)
                        }
                    }
                } else if let error = viewModel.error {
                    LoadingStateView(state: .error(message: error, retry: {
                        if let id = auth.currentUser?.id {
                            await viewModel.loadProfile(entityId: id)
                        }
                    }))
                }
            }
            .navigationTitle("Profile")
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                if auth.isAuthenticated {
                    ToolbarItem(placement: .primaryAction) {
                        NavigationLink {
                            SettingsView()
                        } label: {
                            Image(systemName: "gearshape")
                        }
                        .tint(.agPrimary)
                    }
                }
                if viewModel.profile?.isOwnProfile == true {
                    ToolbarItem(placement: .secondaryAction) {
                        Button {
                            editDisplayName = viewModel.profile?.displayName ?? ""
                            editBio = viewModel.profile?.bioMarkdown ?? ""
                            showEditSheet = true
                        } label: {
                            Image(systemName: "pencil")
                        }
                        .tint(.agPrimary)
                    }
                }
            }
            .sheet(isPresented: $showEditSheet) {
                editProfileSheet
            }
            .task {
                if let id = auth.currentUser?.id {
                    await viewModel.loadProfile(entityId: id)
                }
            }
        }
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

    private var evolutionSection: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: AGSpacing.md) {
                Text("Evolution Timeline")
                    .font(AGTypography.lg)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.agText)

                ForEach(Array(viewModel.evolutionRecords.enumerated()), id: \.element.id) { index, record in
                    HStack(spacing: AGSpacing.md) {
                        Circle()
                            .fill(Color.agPrimary)
                            .frame(width: 8, height: 8)

                        VStack(alignment: .leading, spacing: 2) {
                            Text(record.version)
                                .font(AGTypography.sm)
                                .fontWeight(.medium)
                                .foregroundStyle(Color.agText)
                            Text(record.changeSummary)
                                .font(AGTypography.xs)
                                .foregroundStyle(Color.agMuted)
                        }

                        Spacer()

                        Text(DateFormatting.relativeTime(from: record.createdAt))
                            .font(AGTypography.xs)
                            .foregroundStyle(Color.agMuted)
                    }

                    if index < viewModel.evolutionRecords.count - 1 {
                        Divider()
                            .background(Color.agBorder)
                    }
                }
            }
        }
    }

    private var stagingCTA: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: AGSpacing.md) {
                @Bindable var env = envManager

                Text("Environment")
                    .font(AGTypography.lg)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.agText)

                Picker("Environment", selection: $env.current) {
                    ForEach(ServerEnvironment.allCases, id: \.self) { env in
                        Text(env.displayName).tag(env)
                    }
                }
                .pickerStyle(.segmented)
                .onChange(of: envManager.current) { _, newValue in
                    Task {
                        await APIService.shared.updateEnvironment(newValue)
                        await envManager.checkHealth()
                    }
                }

                HStack {
                    Text("Status:")
                        .font(AGTypography.sm)
                        .foregroundStyle(Color.agMuted)
                    Circle()
                        .fill(healthColor)
                        .frame(width: 8, height: 8)
                    Text(healthText)
                        .font(AGTypography.sm)
                        .foregroundStyle(Color.agMuted)
                }

                Divider().background(Color.agBorder)

                VStack(alignment: .leading, spacing: AGSpacing.xs) {
                    Text("Open Staging Web")
                        .font(AGTypography.sm)
                        .fontWeight(.medium)
                        .foregroundStyle(Color.agText)
                    Text("***REMOVED***:\(envManager.current == .staging ? 5174 : 5173)")
                        .font(AGTypography.xs)
                        .foregroundStyle(Color.agMuted)
                }

                Link(destination: envManager.current.webURL) {
                    HStack {
                        Text("Open in Safari")
                            .font(AGTypography.sm)
                            .fontWeight(.semibold)
                        Image(systemName: "arrow.up.right")
                            .font(AGTypography.xs)
                    }
                    .foregroundStyle(Color.agAccent)
                }
            }
        }
        .task {
            await envManager.checkHealth()
        }
    }

    private var healthColor: Color {
        switch envManager.healthStatus {
        case .connected: return .agSuccess
        case .disconnected: return .agDanger
        case .checking: return .agWarning
        case .unknown: return .agMuted
        }
    }

    private var healthText: String {
        switch envManager.healthStatus {
        case .connected: return "Connected"
        case .disconnected: return "Disconnected"
        case .checking: return "Checking..."
        case .unknown: return "Unknown"
        }
    }

    private var guestProfilePrompt: some View {
        VStack(spacing: AGSpacing.xl) {
            Spacer()

            Image(systemName: "person.circle")
                .font(.system(size: 64))
                .foregroundStyle(Color.agMuted)

            VStack(spacing: AGSpacing.sm) {
                Text("Sign in to view your profile")
                    .font(AGTypography.xl)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.agText)

                Text("Create an account to build your identity, track trust scores, and connect with other agents.")
                    .font(AGTypography.base)
                    .foregroundStyle(Color.agMuted)
                    .multilineTextAlignment(.center)
            }

            Button {
                AnalyticsService.shared.trackEvent(type: "guest_cta_click", page: "profile", intent: "sign_in")
                // #12: exitGuestMode instead of logout
                auth.exitGuestMode()
            } label: {
                Text("Sign In or Register")
                    .fontWeight(.semibold)
                    .frame(maxWidth: .infinity)
                    .padding(AGSpacing.md)
            }
            .buttonStyle(.borderedProminent)
            .tint(.agPrimary)
            .clipShape(RoundedRectangle(cornerRadius: AGRadii.md))

            Spacer()
        }
        .padding(.horizontal, AGSpacing.xl)
    }

    private var editProfileSheet: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()
                VStack(spacing: AGSpacing.lg) {
                    GlassCard {
                        VStack(alignment: .leading, spacing: AGSpacing.md) {
                            Text("Display Name")
                                .font(AGTypography.sm)
                                .foregroundStyle(Color.agMuted)
                            TextField("Name", text: $editDisplayName)
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

                            Text("Bio")
                                .font(AGTypography.sm)
                                .foregroundStyle(Color.agMuted)
                            TextEditor(text: $editBio)
                                .scrollContentBackground(.hidden)
                                .font(AGTypography.base)
                                .foregroundStyle(Color.agText)
                                .frame(minHeight: 100)
                                .padding(AGSpacing.md)
                                .background(Color.agSurface)
                                .clipShape(RoundedRectangle(cornerRadius: AGRadii.md))
                                .overlay(
                                    RoundedRectangle(cornerRadius: AGRadii.md)
                                        .stroke(Color.agBorder, lineWidth: 1)
                                )
                        }
                    }
                    Spacer()
                }
                .padding(AGSpacing.base)
            }
            .navigationTitle("Edit Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { showEditSheet = false }
                        .foregroundStyle(Color.agMuted)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            if let id = auth.currentUser?.id {
                                await viewModel.updateProfile(
                                    entityId: id,
                                    displayName: editDisplayName,
                                    bio: editBio
                                )
                                // #24: Refresh current user after profile edit
                                await auth.refreshCurrentUser()
                                showEditSheet = false
                            }
                        }
                    }
                    .fontWeight(.semibold)
                    .tint(.agPrimary)
                }
            }
        }
    }
}

// MARK: - Stat Card

struct StatCard: View {
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
