// SettingsView — Environment CTA, account management, logout

import SwiftUI

struct SettingsView: View {
    @Environment(AuthViewModel.self) private var auth
    @Environment(EnvironmentManager.self) private var envManager

    var body: some View {
        @Bindable var env = envManager

        ZStack {
            Color.agBackground.ignoresSafeArea()

            ScrollView {
                VStack(spacing: AGSpacing.lg) {
                    // Environment section
                    GlassCard {
                        VStack(alignment: .leading, spacing: AGSpacing.md) {
                            Text("Server Environment")
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
        .toolbarColorScheme(.dark, for: .navigationBar)
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
}
