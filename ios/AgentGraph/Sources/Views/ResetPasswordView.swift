// ResetPasswordView — Deep-linked password reset with token

import SwiftUI

struct ResetPasswordView: View {
    let token: String
    @Environment(\.dismiss) private var dismiss
    @State private var password = ""
    @State private var confirmPassword = ""
    @State private var isSubmitting = false
    @State private var success = false
    @State private var error: String?

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

    private var isFormValid: Bool {
        password.count >= 8 &&
        password.rangeOfCharacter(from: .uppercaseLetters) != nil &&
        password.rangeOfCharacter(from: .lowercaseLetters) != nil &&
        password.rangeOfCharacter(from: .decimalDigits) != nil &&
        password == confirmPassword
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: AGSpacing.lg) {
                        if success {
                            Spacer().frame(height: AGSpacing.huge)

                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 64))
                                .foregroundStyle(Color.agSuccess)

                            Text("Password Reset")
                                .font(AGTypography.xxl)
                                .fontWeight(.semibold)
                                .foregroundStyle(Color.agText)

                            Text("Your password has been updated. You can now sign in with your new password.")
                                .font(AGTypography.base)
                                .foregroundStyle(Color.agMuted)
                                .multilineTextAlignment(.center)

                            Button("Done") {
                                dismiss()
                            }
                            .font(AGTypography.base)
                            .fontWeight(.semibold)
                            .foregroundStyle(Color.agPrimary)
                            .padding(.top, AGSpacing.lg)
                        } else {
                            Spacer().frame(height: AGSpacing.xl)

                            GlassCard {
                                VStack(spacing: AGSpacing.lg) {
                                    Text("New Password")
                                        .font(AGTypography.xl)
                                        .fontWeight(.semibold)
                                        .foregroundStyle(Color.agText)

                                    VStack(alignment: .leading, spacing: AGSpacing.sm) {
                                        Text("Password")
                                            .font(AGTypography.sm)
                                            .foregroundStyle(Color.agMuted)
                                        SecureField("Min 8 characters", text: $password)
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

                                        VStack(alignment: .leading, spacing: 2) {
                                            requirementRow("8+ characters", met: password.count >= 8)
                                            requirementRow("Uppercase letter", met: password.rangeOfCharacter(from: .uppercaseLetters) != nil)
                                            requirementRow("Lowercase letter", met: password.rangeOfCharacter(from: .lowercaseLetters) != nil)
                                            requirementRow("Number", met: password.rangeOfCharacter(from: .decimalDigits) != nil)
                                        }
                                    }

                                    VStack(alignment: .leading, spacing: AGSpacing.sm) {
                                        Text("Confirm Password")
                                            .font(AGTypography.sm)
                                            .foregroundStyle(Color.agMuted)
                                        SecureField("Repeat password", text: $confirmPassword)
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

                                        if !confirmPassword.isEmpty && password != confirmPassword {
                                            Text("Passwords do not match")
                                                .font(AGTypography.xs)
                                                .foregroundStyle(Color.agDanger)
                                        }
                                    }

                                    if let error {
                                        Text(error)
                                            .font(AGTypography.sm)
                                            .foregroundStyle(Color.agDanger)
                                    }

                                    Button {
                                        Task { await submitReset() }
                                    } label: {
                                        Group {
                                            if isSubmitting {
                                                ProgressView()
                                                    .tint(.white)
                                            } else {
                                                Text("Reset Password")
                                                    .fontWeight(.semibold)
                                            }
                                        }
                                        .frame(maxWidth: .infinity)
                                        .padding(AGSpacing.md)
                                    }
                                    .buttonStyle(.borderedProminent)
                                    .tint(.agPrimary)
                                    .clipShape(RoundedRectangle(cornerRadius: AGRadii.md))
                                    .disabled(!isFormValid || isSubmitting)
                                }
                            }
                        }
                    }
                    .padding(.horizontal, AGSpacing.xl)
                }
                .scrollDismissesKeyboard(.interactively)
            }
            .navigationTitle("Reset Password")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
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

    private func submitReset() async {
        isSubmitting = true
        error = nil

        do {
            _ = try await APIService.shared.resetPassword(token: token, newPassword: password)
            success = true
        } catch let apiError as APIError {
            error = apiError.errorDescription
        } catch {
            self.error = error.localizedDescription
        }

        isSubmitting = false
    }
}

// PasswordStrength is now in Components/PasswordStrengthView.swift
