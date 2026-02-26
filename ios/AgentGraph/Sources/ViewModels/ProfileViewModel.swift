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

    func loadProfile(entityId: UUID, currentUserId: UUID? = nil) async {
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

            // Check follow status by scanning followers for our ID
            if !profileResponse.isOwnProfile, let myId = currentUserId {
                do {
                    let followers = try await APIService.shared.getFollowers(entityId: entityId)
                    isFollowing = followers.entities.contains { $0.id == myId }
                } catch {
                    // Non-critical — leave isFollowing as false
                }
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
                // Update local follower count
                if var p = profile {
                    profile = ProfileResponse(
                        id: p.id, type: p.type, displayName: p.displayName,
                        bioMarkdown: p.bioMarkdown, avatarUrl: p.avatarUrl,
                        didWeb: p.didWeb, capabilities: p.capabilities,
                        autonomyLevel: p.autonomyLevel, privacyTier: p.privacyTier,
                        isActive: p.isActive, emailVerified: p.emailVerified,
                        trustScore: p.trustScore, trustComponents: p.trustComponents,
                        badges: p.badges, averageRating: p.averageRating,
                        reviewCount: p.reviewCount, endorsementCount: p.endorsementCount,
                        postCount: p.postCount, followerCount: max(0, p.followerCount - 1),
                        followingCount: p.followingCount, createdAt: p.createdAt,
                        isOwnProfile: p.isOwnProfile
                    )
                }
            } else {
                _ = try await APIService.shared.follow(targetId: targetId)
                isFollowing = true
                if var p = profile {
                    profile = ProfileResponse(
                        id: p.id, type: p.type, displayName: p.displayName,
                        bioMarkdown: p.bioMarkdown, avatarUrl: p.avatarUrl,
                        didWeb: p.didWeb, capabilities: p.capabilities,
                        autonomyLevel: p.autonomyLevel, privacyTier: p.privacyTier,
                        isActive: p.isActive, emailVerified: p.emailVerified,
                        trustScore: p.trustScore, trustComponents: p.trustComponents,
                        badges: p.badges, averageRating: p.averageRating,
                        reviewCount: p.reviewCount, endorsementCount: p.endorsementCount,
                        postCount: p.postCount, followerCount: p.followerCount + 1,
                        followingCount: p.followingCount, createdAt: p.createdAt,
                        isOwnProfile: p.isOwnProfile
                    )
                }
            }
        } catch {
            // Handle 409 conflict (already following/not following)
            if let apiError = error as? APIError,
               case .serverError = apiError {
                isFollowing.toggle() // State was wrong, flip it
            }
            self.error = error.localizedDescription
        }
    }

    func updateProfile(entityId: UUID, displayName: String?, bio: String?, avatarUrl: String? = nil) async {
        do {
            let request = UpdateProfileRequest(displayName: displayName, bioMarkdown: bio, avatarUrl: avatarUrl)
            let updated = try await APIService.shared.updateProfile(entityId: entityId, request: request)
            profile = updated
        } catch {
            self.error = error.localizedDescription
        }
    }
}
