// AuthViewModel — Login state, token management, current user

import Foundation
import Observation

@Observable @MainActor
final class AuthViewModel {
    var isAuthenticated = false
    var currentUser: EntityResponse?
    var isLoading = false
    var error: String?

    func checkExistingSession() async {
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
            isAuthenticated = true
        } catch {
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

    func logout() async {
        _ = KeychainService.delete(key: KeychainService.accessTokenKey)
        _ = KeychainService.delete(key: KeychainService.refreshTokenKey)
        await APIService.shared.clearTokens()
        currentUser = nil
        isAuthenticated = false
        error = nil
    }
}
