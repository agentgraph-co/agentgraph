// AuthViewModel — Login state, token management, current user

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
        await APIService.shared.clearTokens()
        currentUser = nil
        isAuthenticated = false
        isGuestMode = false
        error = nil
    }
}
