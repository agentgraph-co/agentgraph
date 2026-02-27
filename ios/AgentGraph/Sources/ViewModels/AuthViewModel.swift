// AuthViewModel — Login state, token management, current user

import AuthenticationServices
import Foundation
import Observation

@Observable @MainActor
final class AuthViewModel {
    var isAuthenticated = false
    var isGuestMode = false
    var isCheckingSession = true
    var currentUser: EntityResponse?
    var isLoading = false
    var error: String?

    /// Whether the user can access the main app (logged in or guest)
    var canAccessApp: Bool {
        isAuthenticated || isGuestMode
    }

    // #14: Shows loading during session check to avoid login screen flash
    func checkExistingSession() async {
        isCheckingSession = true
        defer { isCheckingSession = false }

        guard let access = KeychainService.load(key: KeychainService.accessTokenKey),
              let refresh = KeychainService.load(key: KeychainService.refreshTokenKey) else {
            return
        }

        await APIService.shared.setTokens(access: access, refresh: refresh)

        do {
            let user = try await APIService.shared.getMe()
            currentUser = user
            isAuthenticated = true
            await connectWebSocket(token: access)
        } catch {
            // Token expired or invalid — try refresh
            do {
                let tokenResponse = try await APIService.shared.refreshTokens()
                await APIService.shared.setTokens(
                    access: tokenResponse.accessToken,
                    refresh: tokenResponse.refreshToken
                )
                _ = KeychainService.save(key: KeychainService.accessTokenKey, value: tokenResponse.accessToken)
                _ = KeychainService.save(key: KeychainService.refreshTokenKey, value: tokenResponse.refreshToken)

                let user = try await APIService.shared.getMe()
                currentUser = user
                isAuthenticated = true
                await connectWebSocket(token: tokenResponse.accessToken)
            } catch {
                // Refresh failed — clear everything
                await logout()
            }
        }
    }

    func enterGuestMode() {
        isGuestMode = true
    }

    // #12: Clean exit from guest mode without touching Keychain
    func exitGuestMode() {
        isGuestMode = false
        isAuthenticated = false
    }

    func signInWithGoogle() async {
        isLoading = true
        error = nil

        let baseURL = await APIService.shared.currentBaseURL()
        let authURL = baseURL.appendingPathComponent("auth/google")
        guard var components = URLComponents(url: authURL, resolvingAgainstBaseURL: false) else {
            error = "Invalid auth URL"
            isLoading = false
            return
        }
        components.queryItems = [URLQueryItem(name: "platform", value: "ios")]
        guard let url = components.url else {
            error = "Invalid auth URL"
            isLoading = false
            return
        }

        let callbackScheme = "com.agentgraph.ios"

        do {
            let callbackURL = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<URL, Error>) in
                let session = ASWebAuthenticationSession(
                    url: url,
                    callbackURLScheme: callbackScheme
                ) { url, error in
                    if let error {
                        continuation.resume(throwing: error)
                    } else if let url {
                        continuation.resume(returning: url)
                    } else {
                        continuation.resume(throwing: URLError(.badServerResponse))
                    }
                }
                session.prefersEphemeralWebBrowserSession = false
                session.presentationContextProvider = GoogleSignInPresenter.shared
                session.start()
            }

            // Parse tokens from callback URL fragment: com.agentgraph.ios://auth/callback#access_token=...&refresh_token=...
            guard let fragment = callbackURL.fragment else {
                error = "No tokens received from Google"
                isLoading = false
                return
            }

            let params = URLComponents(string: "?\(fragment)")?.queryItems ?? []
            let accessToken = params.first(where: { $0.name == "access_token" })?.value
            let refreshToken = params.first(where: { $0.name == "refresh_token" })?.value

            guard let accessToken, let refreshToken else {
                error = "Invalid token response"
                isLoading = false
                return
            }

            _ = KeychainService.save(key: KeychainService.accessTokenKey, value: accessToken)
            _ = KeychainService.save(key: KeychainService.refreshTokenKey, value: refreshToken)
            await APIService.shared.setTokens(access: accessToken, refresh: refreshToken)

            let user = try await APIService.shared.getMe()
            currentUser = user
            isGuestMode = false
            isAuthenticated = true
            await connectWebSocket(token: accessToken)
        } catch {
            if (error as NSError).code == ASWebAuthenticationSessionError.canceledLogin.rawValue {
                // User cancelled — not an error
            } else {
                self.error = error.localizedDescription
            }
        }

        isLoading = false
    }

    func login(email: String, password: String) async {
        isLoading = true
        error = nil

        do {
            let tokenResponse = try await APIService.shared.login(email: email, password: password)
            _ = KeychainService.save(key: KeychainService.accessTokenKey, value: tokenResponse.accessToken)
            _ = KeychainService.save(key: KeychainService.refreshTokenKey, value: tokenResponse.refreshToken)
            await APIService.shared.setTokens(access: tokenResponse.accessToken, refresh: tokenResponse.refreshToken)

            let user = try await APIService.shared.getMe()
            currentUser = user
            isGuestMode = false
            isAuthenticated = true
            await connectWebSocket(token: tokenResponse.accessToken)
        } catch {
            // #8: If token was saved but getMe failed, clean up
            await APIService.shared.clearTokens()
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func register(email: String, password: String, displayName: String) async -> String? {
        isLoading = true
        error = nil

        do {
            let response = try await APIService.shared.register(
                email: email,
                password: password,
                displayName: displayName
            )
            isLoading = false
            return response.message
        } catch {
            self.error = error.localizedDescription
            isLoading = false
            return nil
        }
    }

    // #24: Refresh currentUser after profile edit
    func refreshCurrentUser() async {
        do {
            let user = try await APIService.shared.getMe()
            currentUser = user
        } catch {
            // Non-critical
        }
    }

    func logout() async {
        await WebSocketService.shared.disconnect()
        // Invalidate refresh token on server before clearing locally
        await APIService.shared.serverLogout()
        await APIService.shared.clearTokens()
        currentUser = nil
        isAuthenticated = false
        isGuestMode = false
        error = nil
    }

    // MARK: - WebSocket

    private func connectWebSocket(token: String) async {
        await WebSocketService.shared.connect(
            token: token,
            channels: ["feed", "notifications", "activity", "messages"]
        )
    }

    func reconnectWebSocket() async {
        guard let token = KeychainService.load(key: KeychainService.accessTokenKey) else { return }
        await connectWebSocket(token: token)
    }

    func disconnectWebSocket() async {
        await WebSocketService.shared.disconnect()
    }
}
