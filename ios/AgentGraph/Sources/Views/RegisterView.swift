// RegisterView — Registration with email verification

import SwiftUI

struct RegisterView: View {
    @Environment(AuthViewModel.self) private var auth
    @Environment(\.dismiss) private var dismiss
    @State private var email = ""
    @State private var password = ""
    @State private var displayName = ""
    @State private var successMessage: String?

    var body: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: AGSpacing.lg) {
                        if let successMessage {
                            // Success state
                            GlassCard {
                                VStack(spacing: AGSpacing.lg) {
                                    Image(systemName: "checkmark.circle.fill")
                                        .font(.system(size: 48))
                                        .foregroundStyle(Color.agSuccess)

                                    Text("Account Created")
                                        .font(AGTypography.xl)
                                        .fontWeight(.bold)
                                        .foregroundStyle(Color.agText)

                                    Text(successMessage)
                                        .font(AGTypography.base)
                                        .foregroundStyle(Color.agMuted)
                                        .multilineTextAlignment(.center)

                                    Button("Back to Sign In") {
                                        dismiss()
                                    }
                                    .font(AGTypography.base)
                                    .fontWeight(.semibold)
                                    .foregroundStyle(Color.agPrimary)
                                }
                            }
                        } else {
                            // Registration form
                            GlassCard {
                                VStack(spacing: AGSpacing.lg) {
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
                                            .clipShape(RoundedRectangle(cornerRadius: AGRadius.md))
                                            .overlay(
                                                RoundedRectangle(cornerRadius: AGRadius.md)
                                                    .stroke(Color.agBorder, lineWidth: 1)
                                            )
                                            .textContentType(.name)
                                    }

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
                                        SecureField("Min 8 chars, upper + lower + digit", text: $password)
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
                                            .textContentType(.newPassword)

                                        Text("At least 8 characters with uppercase, lowercase, and a digit")
                                            .font(AGTypography.xs)
                                            .foregroundStyle(Color.agMuted)
                                    }

                                    if let error = auth.error {
                                        Text(error)
                                            .font(AGTypography.sm)
                                            .foregroundStyle(Color.agDanger)
                                    }

                                    Button {
                                        Task {
                                            let message = await auth.register(
                                                email: email,
                                                password: password,
                                                displayName: displayName
                                            )
                                            if let message {
                                                successMessage = message
                                            }
                                        }
                                    } label: {
                                        Group {
                                            if auth.isLoading {
                                                ProgressView()
                                                    .tint(.white)
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
                                    .clipShape(RoundedRectangle(cornerRadius: AGRadius.md))
                                    .disabled(email.isEmpty || password.isEmpty || displayName.isEmpty || auth.isLoading)
                                }
                            }
                        }
                    }
                    .padding(.horizontal, AGSpacing.xl)
                    .padding(.top, AGSpacing.lg)
                }
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
        }
    }
}
