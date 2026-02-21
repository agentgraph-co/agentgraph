// VerifyEmailView — Auto-triggers email verification on appear

import SwiftUI

struct VerifyEmailView: View {
    let token: String
    @Environment(\.dismiss) private var dismiss

    @State private var state: VerifyState = .loading
    @State private var message = ""

    enum VerifyState {
        case loading
        case success
        case error
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                VStack(spacing: AGSpacing.xl) {
                    Spacer()

                    switch state {
                    case .loading:
                        ProgressView()
                            .scaleEffect(1.5)
                            .tint(.agPrimary)

                        Text("Verifying your email...")
                            .font(AGTypography.lg)
                            .foregroundStyle(Color.agText)

                    case .success:
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 64))
                            .foregroundStyle(Color.agSuccess)

                        Text("Email Verified")
                            .font(AGTypography.xxl)
                            .fontWeight(.semibold)
                            .foregroundStyle(Color.agText)

                        Text(message)
                            .font(AGTypography.base)
                            .foregroundStyle(Color.agMuted)
                            .multilineTextAlignment(.center)

                        Button("Continue") {
                            dismiss()
                        }
                        .font(AGTypography.base)
                        .fontWeight(.semibold)
                        .foregroundStyle(Color.agPrimary)
                        .padding(.top, AGSpacing.lg)

                    case .error:
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.system(size: 64))
                            .foregroundStyle(Color.agWarning)

                        Text("Verification Failed")
                            .font(AGTypography.xxl)
                            .fontWeight(.semibold)
                            .foregroundStyle(Color.agText)

                        Text(message)
                            .font(AGTypography.base)
                            .foregroundStyle(Color.agMuted)
                            .multilineTextAlignment(.center)

                        Button("Dismiss") {
                            dismiss()
                        }
                        .font(AGTypography.base)
                        .fontWeight(.semibold)
                        .foregroundStyle(Color.agPrimary)
                        .padding(.top, AGSpacing.lg)
                    }

                    Spacer()
                }
                .padding(.horizontal, AGSpacing.xl)
            }
            .navigationTitle("Email Verification")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .task {
                await verify()
            }
        }
    }

    private func verify() async {
        do {
            let response = try await APIService.shared.verifyEmail(token: token)
            message = response.message
            state = .success
        } catch let apiError as APIError {
            message = apiError.errorDescription ?? "Verification failed. The link may have expired."
            state = .error
        } catch {
            message = error.localizedDescription
            state = .error
        }
    }
}
