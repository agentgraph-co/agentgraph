// ChangePasswordView — Account password change with strength validation

import SwiftUI

struct ChangePasswordView: View {
    @Environment(AuthViewModel.self) private var auth
    @Environment(\.dismiss) private var dismiss
    @State private var currentPassword = ""
    @State private var newPassword = ""
    @State private var confirmPassword = ""
    @State private var isSubmitting = false
    @State private var error: String?
    @State private var success = false

    private var passwordStrength: PasswordStrength {
        let hasUpper = newPassword.rangeOfCharacter(from: .uppercaseLetters) != nil
        let hasLower = newPassword.rangeOfCharacter(from: .lowercaseLetters) != nil
        let hasDigit = newPassword.rangeOfCharacter(from: .decimalDigits) != nil
        let longEnough = newPassword.count >= 8

        if newPassword.isEmpty { return .none }
        let met = [hasUpper, hasLower, hasDigit, longEnough].filter { $0 }.count
        if met <= 1 { return .weak }
        if met <= 3 { return .medium }
        return .strong
    }

    private var isFormValid: Bool {
        !currentPassword.isEmpty &&
        newPassword.count >= 8 &&
        newPassword.rangeOfCharacter(from: .uppercaseLetters) != nil &&
        newPassword.rangeOfCharacter(from: .lowercaseLetters) != nil &&
        newPassword.rangeOfCharacter(from: .decimalDigits) != nil &&
        newPassword == confirmPassword
    }

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            ScrollView {
                VStack(spacing: AGSpacing.lg) {
                    if success {
                        Spacer().frame(height: AGSpacing.huge)

                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 64))
                            .foregroundStyle(Color.agSuccess)

                        Text("Password Changed")
                            .font(AGTypography.xxl)
                            .fontWeight(.semibold)
                            .foregroundStyle(Color.agText)

                        Text("Your password has been updated and all sessions have been invalidated. Please sign in again.")
                            .font(AGTypography.base)
                            .foregroundStyle(Color.agMuted)
                            .multilineTextAlignment(.center)

                        Button("Sign In") {
                            Task { await auth.logout() }
                        }
                        .font(AGTypography.base)
                        .fontWeight(.semibold)
                        .foregroundStyle(Color.agPrimary)
                        .padding(.top, AGSpacing.lg)
                    } else {
                        GlassCard {
                            VStack(spacing: AGSpacing.lg) {
                                // Current password
                                VStack(alignment: .leading, spacing: AGSpacing.sm) {
                                    Text("Current Password")
                                        .font(AGTypography.sm)
                                        .foregroundStyle(Color.agMuted)
                                    SecureField("Enter current password", text: $currentPassword)
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
                                        .submitLabel(.next)
                                }

                                // New password
                                VStack(alignment: .leading, spacing: AGSpacing.sm) {
                                    Text("New Password")
                                        .font(AGTypography.sm)
                                        .foregroundStyle(Color.agMuted)
                                    SecureField("Min 8 characters", text: $newPassword)
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

                                    if !newPassword.isEmpty {
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
                                        requirementRow("8+ characters", met: newPassword.count >= 8)
                                        requirementRow("Uppercase letter", met: newPassword.rangeOfCharacter(from: .uppercaseLetters) != nil)
                                        requirementRow("Lowercase letter", met: newPassword.rangeOfCharacter(from: .lowercaseLetters) != nil)
                                        requirementRow("Number", met: newPassword.rangeOfCharacter(from: .decimalDigits) != nil)
                                    }
                                }

                                // Confirm password
                                VStack(alignment: .leading, spacing: AGSpacing.sm) {
                                    Text("Confirm New Password")
                                        .font(AGTypography.sm)
                                        .foregroundStyle(Color.agMuted)
                                    SecureField("Repeat new password", text: $confirmPassword)
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
                                        .submitLabel(.go)
                                        .onSubmit {
                                            if isFormValid && !isSubmitting {
                                                Task { await submitChange() }
                                            }
                                        }

                                    if !confirmPassword.isEmpty && newPassword != confirmPassword {
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
                                    Task { await submitChange() }
                                } label: {
                                    Group {
                                        if isSubmitting {
                                            ProgressView()
                                                .tint(.white)
                                        } else {
                                            Text("Change Password")
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
                .padding(.top, AGSpacing.lg)
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .navigationTitle("Change Password")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
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

    private func submitChange() async {
        isSubmitting = true
        error = nil

        do {
            _ = try await APIService.shared.changePassword(
                currentPassword: currentPassword,
                newPassword: newPassword
            )
            success = true
        } catch let apiError as APIError {
            error = apiError.errorDescription
        } catch {
            self.error = error.localizedDescription
        }

        isSubmitting = false
    }
}
