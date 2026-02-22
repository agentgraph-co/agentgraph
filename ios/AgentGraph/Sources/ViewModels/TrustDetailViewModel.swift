// TrustDetailViewModel — Trust score breakdown, attestations, and contestation

import Foundation
import Observation

@Observable @MainActor
final class TrustDetailViewModel {
    let entityId: UUID

    var trustScore: TrustScoreResponse?
    var attestations: [AttestationResponse] = []
    var attestationCount: Int = 0
    var isLoading = false
    var isSubmitting = false
    var error: String?
    var contestReason = ""
    var contestSubmitted = false
    var contestError: String?

    // Attestation creation
    var newAttestationType = "competent"
    var newAttestationContext = ""
    var newAttestationComment = ""
    var attestationCreated = false
    var attestationError: String?

    init(entityId: UUID) {
        self.entityId = entityId
    }

    // MARK: - Component Helpers

    /// Ordered list of trust components with their weights and display info
    static let componentDefinitions: [(key: String, label: String, weight: Double)] = [
        ("verification", "Verification", 0.35),
        ("activity", "Activity", 0.20),
        ("community", "Community", 0.20),
        ("reputation", "Reputation", 0.15),
        ("age", "Account Age", 0.10),
    ]

    /// Attestation types for picker
    static let attestationTypes = ["competent", "reliable", "safe", "responsive"]

    // MARK: - Data Loading

    func loadAll() async {
        isLoading = true
        error = nil

        async let trustTask: () = loadTrustScore()
        async let attestTask: () = loadAttestations()

        _ = await (trustTask, attestTask)

        isLoading = false
    }

    func loadTrustScore() async {
        do {
            trustScore = try await APIService.shared.getTrustScore(entityId: entityId)
        } catch {
            self.error = error.localizedDescription
        }
    }

    func loadAttestations() async {
        do {
            let response = try await APIService.shared.getAttestations(entityId: entityId)
            attestations = response.attestations
            attestationCount = response.count
        } catch {
            // Attestations may not exist yet
            attestations = []
            attestationCount = 0
        }
    }

    // MARK: - Actions

    func contestScore() async {
        guard !contestReason.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            contestError = "Please provide a reason (at least 10 characters)."
            return
        }
        guard contestReason.count >= 10 else {
            contestError = "Reason must be at least 10 characters."
            return
        }

        isSubmitting = true
        contestError = nil

        do {
            _ = try await APIService.shared.contestTrustScore(
                entityId: entityId,
                reason: contestReason
            )
            contestSubmitted = true
            contestReason = ""
        } catch {
            contestError = error.localizedDescription
        }

        isSubmitting = false
    }

    func createAttestation() async {
        guard !newAttestationType.isEmpty else {
            attestationError = "Please select an attestation type."
            return
        }

        isSubmitting = true
        attestationError = nil

        do {
            let attestation = try await APIService.shared.createAttestation(
                targetId: entityId,
                type: newAttestationType,
                context: newAttestationContext.isEmpty ? nil : newAttestationContext,
                comment: newAttestationComment.isEmpty ? nil : newAttestationComment
            )
            attestations.insert(attestation, at: 0)
            attestationCount += 1
            attestationCreated = true
            newAttestationContext = ""
            newAttestationComment = ""
        } catch {
            attestationError = error.localizedDescription
        }

        isSubmitting = false
    }

    // MARK: - Grouped Attestations

    var groupedAttestations: [(type: String, items: [AttestationResponse])] {
        let grouped = Dictionary(grouping: attestations) { $0.attestationType }
        return TrustDetailViewModel.attestationTypes.compactMap { type in
            guard let items = grouped[type], !items.isEmpty else { return nil }
            return (type: type, items: items)
        }
    }

    // MARK: - Contextual Scores

    /// Extract contextual scores from attestations by grouping unique contexts
    var contextualScores: [(context: String, count: Int)] {
        let contexts = attestations.compactMap { $0.context }
        let grouped = Dictionary(grouping: contexts) { $0 }
        return grouped.map { (context: $0.key, count: $0.value.count) }
            .sorted { $0.context < $1.context }
    }
}
