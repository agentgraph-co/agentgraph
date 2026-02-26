// SettingsView — Environment CTA, account management, privacy, logout

import SwiftUI

enum PrivacyTier: String, CaseIterable, Identifiable {
    case publicTier = "public"
    case verified = "verified"
    case privateTier = "private"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .publicTier: return "Public"
        case .verified: return "Verified Only"
        case .privateTier: return "Private"
        }
    }

    var description: String {
        switch self {
        case .publicTier: return "Anyone can view your profile and posts"
        case .verified: return "Only verified users can view your full profile"
        case .privateTier: return "Only your followers can view your profile and posts"
        }
    }

    var iconName: String {
        switch self {
        case .publicTier: return "globe"
        case .verified: return "checkmark.shield"
        case .privateTier: return "lock.shield"
        }
    }
}

struct SettingsView: View {
    @Environment(AuthViewModel.self) private var auth
    @Environment(EnvironmentManager.self) private var envManager

    @State private var selectedPrivacyTier: PrivacyTier = .publicTier
    @State private var isLoadingPrivacy = false
    @State private var privacyError: String?

    var body: some View {
        @Bindable var env = envManager

        ZStack {
            Color.agBackground.ignoresSafeArea()

            ScrollView {
                VStack(spacing: AGSpacing.lg) {
                    #if DEBUG
                    // Environment section (debug builds only)
                    GlassCard {
                        VStack(alignment: .leading, spacing: AGSpacing.md) {
                            Text("Server Environment")
                                .font(AGTypography.lg)
                                .fontWeight(.semibold)
                                .foregroundStyle(Color.agText)

                            Picker("Environment", selection: $env.current) {
                                ForEach(ServerEnvironment.selectableCases, id: \.self) { env in
                                    Text(env.displayName).tag(env)
                                }
                            }
                            .pickerStyle(.segmented)
                            .onChange(of: envManager.current) { _, newValue in
                                Task {
                                    // #23: Invalidate tokens and force re-login on env switch
                                    await APIService.shared.updateEnvironment(newValue)
                                    await APIService.shared.clearTokens()
                                    await auth.logout()
                                    await envManager.checkHealth()
                                }
                            }

                            HStack {
                                Circle()
                                    .fill(healthColor)
                                    .frame(width: 8, height: 8)
                                Text(healthText)
                                    .font(AGTypography.sm)
                                    .foregroundStyle(Color.agMuted)
                                Spacer()
                                Text(":\(envManager.current.port)")
                                    .font(AGTypography.xs)
                                    .foregroundStyle(Color.agMuted)
                            }
                        }
                    }
                    #endif

                    // Account section
                    GlassCard {
                        VStack(alignment: .leading, spacing: AGSpacing.md) {
                            Text("Account")
                                .font(AGTypography.lg)
                                .fontWeight(.semibold)
                                .foregroundStyle(Color.agText)

                            if let user = auth.currentUser {
                                HStack {
                                    Text("Email")
                                        .font(AGTypography.sm)
                                        .foregroundStyle(Color.agMuted)
                                    Spacer()
                                    Text(user.email ?? "N/A")
                                        .font(AGTypography.sm)
                                        .foregroundStyle(Color.agText)
                                }

                                HStack {
                                    Text("Type")
                                        .font(AGTypography.sm)
                                        .foregroundStyle(Color.agMuted)
                                    Spacer()
                                    Text(user.type.capitalized)
                                        .font(AGTypography.sm)
                                        .foregroundStyle(Color.agText)
                                }

                                HStack {
                                    Text("Member since")
                                        .font(AGTypography.sm)
                                        .foregroundStyle(Color.agMuted)
                                    Spacer()
                                    Text(user.createdAt, style: .date)
                                        .font(AGTypography.sm)
                                        .foregroundStyle(Color.agText)
                                }
                            }

                            Divider().background(Color.agBorder)

                            NavigationLink {
                                ChangePasswordView()
                            } label: {
                                HStack {
                                    Image(systemName: "lock.rotation")
                                        .foregroundStyle(Color.agPrimary)
                                    Text("Change Password")
                                        .font(AGTypography.sm)
                                        .foregroundStyle(Color.agText)
                                    Spacer()
                                    Image(systemName: "chevron.right")
                                        .font(AGTypography.xs)
                                        .foregroundStyle(Color.agMuted)
                                }
                            }

                            NavigationLink {
                                BookmarksView()
                            } label: {
                                HStack {
                                    Image(systemName: "bookmark")
                                        .foregroundStyle(Color.agPrimary)
                                    Text("Bookmarks")
                                        .font(AGTypography.sm)
                                        .foregroundStyle(Color.agText)
                                    Spacer()
                                    Image(systemName: "chevron.right")
                                        .font(AGTypography.xs)
                                        .foregroundStyle(Color.agMuted)
                                }
                            }

                            NavigationLink {
                                AgentManagementView()
                            } label: {
                                HStack {
                                    Image(systemName: "cpu")
                                        .foregroundStyle(Color.agPrimary)
                                    Text("My Agents")
                                        .font(AGTypography.sm)
                                        .foregroundStyle(Color.agText)
                                    Spacer()
                                    Image(systemName: "chevron.right")
                                        .font(AGTypography.xs)
                                        .foregroundStyle(Color.agMuted)
                                }
                            }

                            NavigationLink {
                                PurchaseHistoryView()
                            } label: {
                                HStack {
                                    Image(systemName: "bag")
                                        .foregroundStyle(Color.agPrimary)
                                    Text("Purchase History")
                                        .font(AGTypography.sm)
                                        .foregroundStyle(Color.agText)
                                    Spacer()
                                    Image(systemName: "chevron.right")
                                        .font(AGTypography.xs)
                                        .foregroundStyle(Color.agMuted)
                                }
                            }
                        }
                    }

                    // Privacy section
                    GlassCard {
                        VStack(alignment: .leading, spacing: AGSpacing.md) {
                            Text("Privacy")
                                .font(AGTypography.lg)
                                .fontWeight(.semibold)
                                .foregroundStyle(Color.agText)

                            Text("Control who can view your profile and content.")
                                .font(AGTypography.xs)
                                .foregroundStyle(Color.agMuted)

                            ForEach(PrivacyTier.allCases) { tier in
                                Button {
                                    Task { await updatePrivacy(tier) }
                                } label: {
                                    HStack(spacing: AGSpacing.sm) {
                                        Image(systemName: tier.iconName)
                                            .font(AGTypography.base)
                                            .foregroundStyle(
                                                selectedPrivacyTier == tier
                                                    ? Color.agPrimary
                                                    : Color.agMuted
                                            )
                                            .frame(width: 24)

                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(tier.displayName)
                                                .font(AGTypography.sm)
                                                .fontWeight(.medium)
                                                .foregroundStyle(Color.agText)
                                            Text(tier.description)
                                                .font(AGTypography.xs)
                                                .foregroundStyle(Color.agMuted)
                                        }

                                        Spacer()

                                        if selectedPrivacyTier == tier {
                                            Image(systemName: "checkmark.circle.fill")
                                                .foregroundStyle(Color.agPrimary)
                                        }
                                    }
                                    .padding(AGSpacing.sm)
                                    .background(
                                        RoundedRectangle(cornerRadius: 8)
                                            .stroke(
                                                selectedPrivacyTier == tier
                                                    ? Color.agPrimary
                                                    : Color.agBorder,
                                                lineWidth: 1
                                            )
                                    )
                                }
                                .disabled(isLoadingPrivacy)
                            }

                            if let error = privacyError {
                                Text(error)
                                    .font(AGTypography.xs)
                                    .foregroundStyle(Color.agDanger)
                            }
                        }
                    }

                    // Logout
                    Button {
                        Task { await auth.logout() }
                    } label: {
                        HStack {
                            Image(systemName: "rectangle.portrait.and.arrow.right")
                            Text("Sign Out")
                        }
                        .font(AGTypography.base)
                        .fontWeight(.semibold)
                        .foregroundStyle(Color.agDanger)
                        .frame(maxWidth: .infinity)
                        .padding(AGSpacing.md)
                    }
                    .glassCard()

                    // App info
                    VStack(spacing: AGSpacing.xs) {
                        Text("AgentGraph iOS")
                            .font(AGTypography.xs)
                            .foregroundStyle(Color.agMuted)
                        Text("v0.1.0")
                            .font(AGTypography.xs)
                            .foregroundStyle(Color.agMuted)
                    }
                    .padding(.top, AGSpacing.lg)
                }
                .padding(.horizontal, AGSpacing.base)
                .padding(.top, AGSpacing.sm)
            }
        }
        .navigationTitle("Settings")
        // #41: Inline title display mode
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .task {
            await envManager.checkHealth()
            await loadPrivacy()
        }
    }

    private func loadPrivacy() async {
        do {
            let response = try await APIService.shared.getPrivacyTier()
            if let tier = PrivacyTier(rawValue: response.tier) {
                selectedPrivacyTier = tier
            }
        } catch {
            // Non-critical — default to public
        }
    }

    private func updatePrivacy(_ tier: PrivacyTier) async {
        isLoadingPrivacy = true
        privacyError = nil
        do {
            _ = try await APIService.shared.updatePrivacyTier(tier: tier.rawValue)
            selectedPrivacyTier = tier
        } catch {
            privacyError = error.localizedDescription
        }
        isLoadingPrivacy = false
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
}
