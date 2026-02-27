// RegisterView — Registration with auto-login on success

import SwiftUI

struct RegisterView: View {
    @Environment(AuthViewModel.self) private var auth
    @Environment(\.dismiss) private var dismiss
    @State private var email = ""
    @State private var password = ""
    @State private var displayName = ""
    @State private var isRegistering = false
    @State private var registrationError: String?

    // #42: Email validation
    private var isEmailValid: Bool {
        let trimmed = email.trimmingCharacters(in: .whitespaces)
        return trimmed.contains("@") && trimmed.contains(".")
    }

    private var isFormValid: Bool {
        isEmailValid && !password.isEmpty && !displayName.isEmpty && password.count >= 8
    }

    private var passwordStrength: PasswordStrength {
        let hasUpper = password.rangeOfCharacter(from: .uppercaseLetters) != nil
        let hasLower = password.rangeOfCharacter(from: .lowercaseLetters) != nil
        let hasDigit = password.rangeOfCharacter(from: .decimalDigits) != nil
        let longEnough = password.count >= 8

        if password.isEmpty { return .none }
        let met = [hasUpper, hasLower, hasDigit, longEnough].filter { $0 }.count
        if met <= 1 { return .weak }
        if met <= 3 { return .medium }
        return .strong
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: AGSpacing.lg) {
                        GlassCard {
                            VStack(spacing: AGSpacing.lg) {
                                // Display Name
                                VStack(alignment: .leading, spacing: AGSpacing.sm) {
                                    Text("Display Name")
                                        .font(AGTypography.sm)
                                        .foregroundStyle(Color.agMuted)
                                    TextField("Your name", text: $displayName)
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
                                        .textContentType(.name)
                                        .submitLabel(.next)
                                        // #29: Clear error on typing
                                        .onChange(of: displayName) { _, _ in
                                            registrationError = nil
                                        }
                                }

                                // Email
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
                                        .submitLabel(.next)
                                        // #29: Clear error on typing
                                        .onChange(of: email) { _, _ in
                                            registrationError = nil
                                        }
                                }

                                // Password with strength indicator
                                VStack(alignment: .leading, spacing: AGSpacing.sm) {
                                    Text("Password")
                                        .font(AGTypography.sm)
                                        .foregroundStyle(Color.agMuted)
                                    SecureField("Min 8 chars, upper + lower + digit", text: $password)
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
                                        .textContentType(.newPassword)
                                        // #13: Submit triggers registration
                                        .submitLabel(.go)
                                        .onSubmit {
                                            if isFormValid && !isRegistering {
                                                Task { await registerAndLogin() }
                                            }
                                        }
                                        // #29: Clear error on typing
                                        .onChange(of: password) { _, _ in
                                            registrationError = nil
                                        }

                                    // Password strength bar
                                    if !password.isEmpty {
                                        HStack(spacing: AGSpacing.xs) {
                                            ForEach(0..<3, id: \.self) { index in
                                                RoundedRectangle(cornerRadius: 2)
                                                    .fill(index < passwordStrength.bars ? passwordStrength.color : Color.agBorder)
                                                    .frame(height: 3)
                                            }
                                            Text(passwordStrength.label)
                                                .font(AGTypography.xs)
                                                .foregroundStyle(passwordStrength.color)
                                        }
                                    }

                                    // Requirements checklist
                                    VStack(alignment: .leading, spacing: 2) {
                                        requirementRow("8+ characters", met: password.count >= 8)
                                        requirementRow("Uppercase letter", met: password.rangeOfCharacter(from: .uppercaseLetters) != nil)
                                        requirementRow("Lowercase letter", met: password.rangeOfCharacter(from: .lowercaseLetters) != nil)
                                        requirementRow("Number", met: password.rangeOfCharacter(from: .decimalDigits) != nil)
                                    }
                                }

                                // Error
                                if let registrationError {
                                    HStack(spacing: AGSpacing.sm) {
                                        Image(systemName: "exclamationmark.triangle.fill")
                                            .foregroundStyle(Color.agDanger)
                                        Text(registrationError)
                                            .font(AGTypography.sm)
                                            .foregroundStyle(Color.agDanger)
                                    }
                                }

                                // Divider
                                HStack {
                                    Rectangle().fill(Color.agBorder).frame(height: 1)
                                    Text("or")
                                        .font(AGTypography.xs)
                                        .foregroundStyle(Color.agMuted)
                                    Rectangle().fill(Color.agBorder).frame(height: 1)
                                }

                                // Google Sign-Up
                                Button {
                                    Task { await auth.signInWithGoogle() }
                                } label: {
                                    HStack(spacing: AGSpacing.sm) {
                                        GoogleLogo()
                                            .frame(width: 18, height: 18)
                                        Text("Sign up with Google")
                                            .fontWeight(.medium)
                                    }
                                    .frame(maxWidth: .infinity)
                                    .padding(AGSpacing.md)
                                }
                                .buttonStyle(.bordered)
                                .tint(.white)
                                .foregroundStyle(Color(.label))
                                .background(Color.white)
                                .clipShape(RoundedRectangle(cornerRadius: AGRadii.md))
                                .disabled(isRegistering || auth.isLoading)

                                // Submit button
                                Button {
                                    Task { await registerAndLogin() }
                                } label: {
                                    Group {
                                        if isRegistering {
                                            HStack(spacing: AGSpacing.sm) {
                                                ProgressView()
                                                    .tint(.white)
                                                Text("Creating account...")
                                                    .fontWeight(.semibold)
                                            }
                                        } else {
                                            Text("Create Account")
                                                .fontWeight(.semibold)
                                        }
                                    }
                                    .frame(maxWidth: .infinity)
                                    .padding(AGSpacing.md)
                                }
                                .buttonStyle(.borderedProminent)
                                .tint(.agPrimary)
                                .clipShape(RoundedRectangle(cornerRadius: AGRadii.md))
                                .disabled(!isFormValid || isRegistering)
                            }
                        }
                    }
                    .padding(.horizontal, AGSpacing.xl)
                    .padding(.top, AGSpacing.lg)
                }
                // #13: Dismiss keyboard on scroll
                .scrollDismissesKeyboard(.interactively)
            }
            .navigationTitle("Create Account")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .foregroundStyle(Color.agMuted)
                }
            }
            .onAppear {
                AnalyticsService.shared.trackEvent(type: "register_start", page: "register")
            }
        }
    }

    private func requirementRow(_ text: String, met: Bool) -> some View {
        HStack(spacing: AGSpacing.xs) {
            Image(systemName: met ? "checkmark.circle.fill" : "circle")
                .font(.system(size: 10))
                .foregroundStyle(met ? Color.agSuccess : Color.agMuted)
            Text(text)
                .font(AGTypography.xs)
                .foregroundStyle(met ? Color.agText : Color.agMuted)
        }
    }

    private func registerAndLogin() async {
        isRegistering = true
        registrationError = nil

        do {
            // Step 1: Register
            _ = try await APIService.shared.register(
                email: email,
                password: password,
                displayName: displayName
            )

            // Step 2: Auto-login immediately
            await auth.login(email: email, password: password)

            if auth.isAuthenticated {
                AnalyticsService.shared.trackEvent(type: "register_complete", page: "register")
                dismiss()
            } else {
                // Login failed after registration (shouldn't happen but handle gracefully)
                registrationError = auth.error ?? "Account created but auto-login failed. Please sign in manually."
            }
        } catch let error as APIError {
            registrationError = error.errorDescription ?? error.localizedDescription
        } catch {
            registrationError = error.localizedDescription
        }

        isRegistering = false
    }
}

// PasswordStrength is now in Components/PasswordStrengthView.swift
