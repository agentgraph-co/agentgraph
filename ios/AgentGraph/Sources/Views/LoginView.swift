// LoginView — Email/password login form with glass styling

import SwiftUI

struct LoginView: View {
    @Environment(AuthViewModel.self) private var auth
    @State private var email = ""
    @State private var password = ""
    @State private var showRegister = false

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
                                    .clipShape(RoundedRectangle(cornerRadius: AGRadius.md))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: AGRadius.md)
                                            .stroke(Color.agBorder, lineWidth: 1)
                                    )
                                    .textContentType(.emailAddress)
                                    .keyboardType(.emailAddress)
                                    .autocorrectionDisabled()
                                    .textInputAutocapitalization(.never)
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
                                    .clipShape(RoundedRectangle(cornerRadius: AGRadius.md))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: AGRadius.md)
                                            .stroke(Color.agBorder, lineWidth: 1)
                                    )
                                    .textContentType(.password)
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
                            .clipShape(RoundedRectangle(cornerRadius: AGRadius.md))
                            .disabled(email.isEmpty || password.isEmpty || auth.isLoading)

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
                }
                .padding(.horizontal, AGSpacing.xl)
            }
        }
        .sheet(isPresented: $showRegister) {
            RegisterView()
        }
    }
}
