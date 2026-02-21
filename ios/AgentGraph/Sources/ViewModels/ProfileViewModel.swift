// ProfileViewModel — Load profile, follow/unfollow, edit

import Foundation
import Observation

@Observable @MainActor
final class ProfileViewModel {
    var profile: ProfileResponse?
    var evolutionRecords: [EvolutionResponse] = []
    var isLoading = false
    var error: String?
    var isFollowing = false

    func loadProfile(entityId: UUID) async {
        isLoading = true
        error = nil

        do {
            let profileResponse = try await APIService.shared.getProfile(entityId: entityId)
            profile = profileResponse

            // Load evolution timeline
            do {
                let timeline = try await APIService.shared.getEvolutionTimeline(entityId: entityId)
                evolutionRecords = timeline.records
            } catch {
                // Evolution may not exist for all entities
                evolutionRecords = []
            }
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func toggleFollow(targetId: UUID) async {
        do {
            if isFollowing {
                _ = try await APIService.shared.unfollow(targetId: targetId)
                isFollowing = false
            } else {
                _ = try await APIService.shared.follow(targetId: targetId)
                isFollowing = true
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func updateProfile(entityId: UUID, displayName: String?, bio: String?) async {
        do {
            let request = UpdateProfileRequest(displayName: displayName, bioMarkdown: bio)
            let updated = try await APIService.shared.updateProfile(entityId: entityId, request: request)
            profile = updated
        } catch {
            self.error = error.localizedDescription
        }
    }
}
