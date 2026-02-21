// ForgotPasswordView — Email form for password reset request

import SwiftUI

struct ForgotPasswordView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var email = ""
    @State private var isSubmitting = false
    @State private var submitted = false
    @State private var error: String?

    private var isEmailValid: Bool {
        let trimmed = email.trimmingCharacters(in: .whitespaces)
        return trimmed.contains("@") && trimmed.contains(".")
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: AGSpacing.lg) {
                        if submitted {
                            // Confirmation state — always shown to prevent enumeration
                            VStack(spacing: AGSpacing.lg) {
                                Spacer().frame(height: AGSpacing.huge)

                                Image(systemName: "envelope.badge.fill")
                                    .font(.system(size: 56))
                                    .foregroundStyle(Color.agSuccess)

                                Text("Check your email")
                                    .font(AGTypography.xxl)
                                    .fontWeight(.semibold)
                                    .foregroundStyle(Color.agText)

                                Text("If an account exists with that email, we've sent a password reset link.")
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
                            }
                        } else {
                            Spacer().frame(height: AGSpacing.xl)

                            GlassCard {
                                VStack(spacing: AGSpacing.lg) {
                                    Text("Reset Password")
                                        .font(AGTypography.xl)
                                        .fontWeight(.semibold)
                                        .foregroundStyle(Color.agText)

                                    Text("Enter your email address and we'll send you a link to reset your password.")
                                        .font(AGTypography.sm)
                                        .foregroundStyle(Color.agMuted)
                                        .multilineTextAlignment(.center)

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
                                            .submitLabel(.go)
                                            .onSubmit {
                                                if isEmailValid && !isSubmitting {
                                                    Task { await submitReset() }
                                                }
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
                                                Text("Send Reset Link")
                                                    .fontWeight(.semibold)
                                            }
                                        }
                                        .frame(maxWidth: .infinity)
                                        .padding(AGSpacing.md)
                                    }
                                    .buttonStyle(.borderedProminent)
                                    .tint(.agPrimary)
                                    .clipShape(RoundedRectangle(cornerRadius: AGRadii.md))
                                    .disabled(!isEmailValid || isSubmitting)
                                }
                            }
                        }
                    }
                    .padding(.horizontal, AGSpacing.xl)
                }
                .scrollDismissesKeyboard(.interactively)
            }
            .navigationTitle("Forgot Password")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .foregroundStyle(Color.agMuted)
                }
            }
        }
    }

    private func submitReset() async {
        isSubmitting = true
        error = nil

        do {
            _ = try await APIService.shared.forgotPassword(email: email)
        } catch {
            // Always show success to prevent email enumeration
        }

        // Always show confirmation regardless of result
        submitted = true
        isSubmitting = false
    }
}
