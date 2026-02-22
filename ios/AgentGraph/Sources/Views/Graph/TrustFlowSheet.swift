// TrustFlowSheet — Bottom sheet showing trust attestation chain on node long-press

import SwiftUI

struct TrustFlowSheet: View {
    let trustFlow: TrustFlowResponse
    var onDismiss: (() -> Void)?
    var onNodeTap: ((String) -> Void)?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AGSpacing.base) {
                    // Header: target entity trust score
                    trustScoreHeader

                    if trustFlow.attestations.isEmpty {
                        emptyState
                    } else {
                        // Trust chain visualization
                        VStack(alignment: .leading, spacing: AGSpacing.xs) {
                            Text("Trust Chain")
                                .font(AGTypography.sm)
                                .fontWeight(.semibold)
                                .foregroundStyle(Color.agText)
                                .padding(.horizontal, AGSpacing.base)

                            ForEach(Array(trustFlow.attestations.enumerated()), id: \.offset) { index, attestation in
                                attestationRow(attestation, depth: 0, index: index)
                            }
                        }
                    }
                }
                .padding(.vertical, AGSpacing.base)
            }
            .background(Color.agBackground)
            .navigationTitle("Trust Flow")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") {
                        onDismiss?()
                    }
                    .foregroundStyle(Color.agPrimary)
                }
            }
            .toolbarColorScheme(.dark, for: .navigationBar)
        }
    }

    // MARK: - Trust Score Header

    private var trustScoreHeader: some View {
        GlassCard {
            VStack(spacing: AGSpacing.sm) {
                Text("Entity Trust Score")
                    .font(AGTypography.xs)
                    .foregroundStyle(Color.agMuted)

                if let score = trustFlow.trustScore {
                    Text(String(format: "%.3f", score))
                        .font(AGTypography.xxl)
                        .fontWeight(.bold)
                        .foregroundStyle(trustScoreColor(score))
                } else {
                    Text("N/A")
                        .font(AGTypography.xxl)
                        .fontWeight(.bold)
                        .foregroundStyle(Color.agMuted)
                }

                Text("\(trustFlow.attestations.count) direct attestation\(trustFlow.attestations.count == 1 ? "" : "s")")
                    .font(AGTypography.xs)
                    .foregroundStyle(Color.agMuted)
            }
            .frame(maxWidth: .infinity)
        }
        .padding(.horizontal, AGSpacing.base)
    }

    // MARK: - Attestation Row (Recursive)

    private func attestationRow(_ attestation: TrustFlowAttestation, depth: Int, index: Int) -> some View {
        VStack(alignment: .leading, spacing: AGSpacing.xs) {
            // Connector line
            HStack(spacing: AGSpacing.sm) {
                // Indentation
                ForEach(0..<depth, id: \.self) { _ in
                    Rectangle()
                        .fill(Color.agBorder.opacity(0.3))
                        .frame(width: 2)
                        .padding(.leading, AGSpacing.base)
                }

                // Arrow connector
                VStack(spacing: 0) {
                    if depth > 0 || index > 0 {
                        Rectangle()
                            .fill(Color.agBorder.opacity(0.5))
                            .frame(width: 2, height: 8)
                    }
                    Image(systemName: "arrow.down.circle.fill")
                        .font(.system(size: 12))
                        .foregroundStyle(attestationTypeColor(attestation.attestationType))
                }

                VStack(alignment: .leading, spacing: 2) {
                    Button {
                        onNodeTap?(attestation.attesterId)
                    } label: {
                        Text(attestation.attesterName)
                            .font(AGTypography.sm)
                            .fontWeight(.medium)
                            .foregroundStyle(Color.agPrimary)
                    }

                    HStack(spacing: AGSpacing.sm) {
                        // Attestation type badge
                        Text(formatAttestationType(attestation.attestationType))
                            .font(AGTypography.xs)
                            .padding(.horizontal, AGSpacing.sm)
                            .padding(.vertical, 2)
                            .background(
                                Capsule()
                                    .fill(attestationTypeColor(attestation.attestationType).opacity(0.15))
                            )
                            .foregroundStyle(attestationTypeColor(attestation.attestationType))

                        // Weight
                        HStack(spacing: 2) {
                            Image(systemName: "scalemass")
                                .font(.system(size: 9))
                            Text(String(format: "%.2f", attestation.weight))
                                .font(AGTypography.xs)
                        }
                        .foregroundStyle(Color.agMuted)
                    }
                }
            }
            .padding(.horizontal, AGSpacing.base)

            // Recursive children
            ForEach(Array(attestation.children.enumerated()), id: \.offset) { childIndex, child in
                attestationRow(child, depth: depth + 1, index: childIndex)
            }
        }
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: AGSpacing.md) {
            Image(systemName: "shield.slash")
                .font(.system(size: 36))
                .foregroundStyle(Color.agMuted)

            Text("No Trust Attestations")
                .font(AGTypography.base)
                .foregroundStyle(Color.agText)

            Text("This entity has not received any trust attestations yet.")
                .font(AGTypography.sm)
                .foregroundStyle(Color.agMuted)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, AGSpacing.xxl)
    }

    // MARK: - Helpers

    private func trustScoreColor(_ score: Double) -> Color {
        if score >= 0.8 { return .agSuccess }
        if score >= 0.5 { return .agWarning }
        return .agDanger
    }

    private func attestationTypeColor(_ type: String) -> Color {
        switch type {
        case "vouch":
            return .agSuccess
        case "skill_endorsement":
            return .agPrimary
        case "identity_verification":
            return Color(red: 0.537, green: 0.706, blue: 0.980) // Blue
        case "reliability":
            return Color(red: 0.580, green: 0.886, blue: 0.835) // Teal
        case "warning":
            return .agWarning
        case "dispute":
            return .agDanger
        default:
            return .agMuted
        }
    }

    private func formatAttestationType(_ type: String) -> String {
        type.replacingOccurrences(of: "_", with: " ").capitalized
    }
}
