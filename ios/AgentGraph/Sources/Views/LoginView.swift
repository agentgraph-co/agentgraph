// LoginView — Email/password login form with glass styling

import SwiftUI

struct LoginView: View {
    @Environment(AuthViewModel.self) private var auth
    @Environment(EnvironmentManager.self) private var envManager
    @State private var email = ""
    @State private var password = ""
    @State private var showRegister = false
    @State private var showForgotPassword = false

    // #42: Basic email validation
    private var isEmailValid: Bool {
        let trimmed = email.trimmingCharacters(in: .whitespaces)
        return trimmed.contains("@") && trimmed.contains(".")
    }

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            ScrollView {
                VStack(spacing: AGSpacing.xl) {
                    Spacer().frame(height: AGSpacing.huge)

                    // Logo
                    VStack(spacing: AGSpacing.md) {
                        Image(systemName: "chart.dots.scatter")
                            .font(.system(size: 56))
                            .foregroundStyle(
                                LinearGradient(
                                    colors: [.agPrimary, .agAccent],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )

                        Text("AgentGraph")
                            .font(AGTypography.hero)
                            .foregroundStyle(Color.agText)

                        Text("Trust infrastructure for AI agents")
                            .font(AGTypography.base)
                            .foregroundStyle(Color.agMuted)
                    }

                    Spacer().frame(height: AGSpacing.lg)

                    // Login form
                    GlassCard {
                        VStack(spacing: AGSpacing.lg) {
                            VStack(alignment: .leading, spacing: AGSpacing.sm) {
                                Text("Email")
                                    .font(AGTypography.sm)
                                    .foregroundStyle(Color.agMuted)
                                TextField("you@example.com", text: $email)
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
                                    .textContentType(.emailAddress)
                                    .keyboardType(.emailAddress)
                                    .autocorrectionDisabled()
                                    .textInputAutocapitalization(.never)
                                    // #13: Submit on return key
                                    .submitLabel(.next)
                                    // #29: Clear error on typing
                                    .onChange(of: email) { _, _ in
                                        if auth.error != nil {
                                            auth.error = nil
                                        }
                                    }
                            }

                            VStack(alignment: .leading, spacing: AGSpacing.sm) {
                                Text("Password")
                                    .font(AGTypography.sm)
                                    .foregroundStyle(Color.agMuted)
                                SecureField("Password", text: $password)
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
                                    .textContentType(.password)
                                    // #13: Submit triggers login
                                    .submitLabel(.go)
                                    .onSubmit {
                                        if isEmailValid && !password.isEmpty && !auth.isLoading {
                                            Task { await auth.login(email: email, password: password) }
                                        }
                                    }
                                    // #29: Clear error on typing
                                    .onChange(of: password) { _, _ in
                                        if auth.error != nil {
                                            auth.error = nil
                                        }
                                    }
                            }

                            if let error = auth.error {
                                Text(error)
                                    .font(AGTypography.sm)
                                    .foregroundStyle(Color.agDanger)
                            }

                            Button {
                                Task { await auth.login(email: email, password: password) }
                            } label: {
                                Group {
                                    if auth.isLoading {
                                        ProgressView()
                                            .tint(.white)
                                    } else {
                                        Text("Sign In")
                                            .fontWeight(.semibold)
                                    }
                                }
                                .frame(maxWidth: .infinity)
                                .padding(AGSpacing.md)
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.agPrimary)
                            .clipShape(RoundedRectangle(cornerRadius: AGRadii.md))
                            .disabled(!isEmailValid || password.isEmpty || auth.isLoading)

                            Button("Forgot password?") {
                                showForgotPassword = true
                            }
                            .font(AGTypography.xs)
                            .foregroundStyle(Color.agMuted)
                            .frame(maxWidth: .infinity, alignment: .trailing)

                            Button("Create Account") {
                                showRegister = true
                            }
                            .font(AGTypography.sm)
                            .foregroundStyle(Color.agAccent)
                        }
                    }

                    // Guest browsing option
                    Button {
                        auth.enterGuestMode()
                    } label: {
                        HStack(spacing: AGSpacing.sm) {
                            Image(systemName: "eye")
                            Text("Browse as Guest")
                        }
                        .font(AGTypography.sm)
                        .foregroundStyle(Color.agMuted)
                    }
                    .padding(.top, AGSpacing.sm)

                    // Environment picker
                    @Bindable var env = envManager
                    HStack(spacing: AGSpacing.sm) {
                        Image(systemName: "server.rack")
                            .foregroundStyle(Color.agMuted)
                        Picker("Server", selection: $env.current) {
                            ForEach(ServerEnvironment.allCases, id: \.self) { environment in
                                Text(environment.displayName).tag(environment)
                            }
                        }
                        .pickerStyle(.segmented)
                        .onChange(of: envManager.current) { _, newEnv in
                            Task {
                                await APIService.shared.updateEnvironment(newEnv)
                                await envManager.checkHealth()
                            }
                        }
                    }
                    .padding(.top, AGSpacing.sm)

                    // Health status indicator
                    HStack(spacing: AGSpacing.xs) {
                        Circle()
                            .fill(envManager.healthStatus == .connected ? Color.agSuccess :
                                  envManager.healthStatus == .checking ? Color.agWarning :
                                  Color.agDanger)
                            .frame(width: 8, height: 8)
                        Text(envManager.current.baseURL.host ?? "")
                            .font(AGTypography.xs)
                            .foregroundStyle(Color.agMuted)
                        Text(":\(envManager.current.port)")
                            .font(AGTypography.xs)
                            .foregroundStyle(Color.agMuted)
                    }
                }
                .padding(.horizontal, AGSpacing.xl)
            }
            // #13: Dismiss keyboard on scroll
            .scrollDismissesKeyboard(.interactively)
        }
        .sheet(isPresented: $showRegister) {
            RegisterView()
        }
        .sheet(isPresented: $showForgotPassword) {
            ForgotPasswordView()
        }
        .onAppear {
            AnalyticsService.shared.trackEvent(type: "login_start", page: "login")
        }
        .onChange(of: auth.isAuthenticated) { _, isAuth in
            if isAuth {
                AnalyticsService.shared.trackEvent(type: "login_complete", page: "login")
            }
        }
        .task {
            await envManager.checkHealth()
        }
    }
}
