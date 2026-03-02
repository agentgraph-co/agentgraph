// EntityRow — Reusable entity row for lists

import SwiftUI

struct EntityRow: View {
    let id: UUID
    let displayName: String
    let type: String
    let didWeb: String?
    let trustScore: Double?
    let avatarUrl: String?

    // #31: Fallback for empty displayName
    private var safeName: String {
        displayName.isEmpty ? "Unknown" : displayName
    }

    init(entity: EntitySummary, trustScore: Double? = nil) {
        self.id = entity.id
        self.displayName = entity.displayName
        self.type = entity.type
        self.didWeb = entity.didWeb
        self.trustScore = trustScore
        self.avatarUrl = entity.avatarUrl
    }

    init(entity: SearchEntityResult) {
        self.id = entity.id
        self.displayName = entity.displayName
        self.type = entity.type
        self.didWeb = entity.didWeb
        self.trustScore = entity.trustScore
        self.avatarUrl = entity.avatarUrl
    }

    init(id: UUID, displayName: String, type: String, didWeb: String? = nil, trustScore: Double? = nil, avatarUrl: String? = nil) {
        self.id = id
        self.displayName = displayName
        self.type = type
        self.didWeb = didWeb
        self.trustScore = trustScore
        self.avatarUrl = avatarUrl
    }

    var body: some View {
        // #33: Removed internal padding — parent GlassCard handles it
        HStack(spacing: AGSpacing.md) {
            if let avatarUrlStr = avatarUrl, let url = URL(string: avatarUrlStr) {
                AsyncImage(url: url) { image in
                    image
                        .resizable()
                        .scaledToFill()
                } placeholder: {
                    initialCircle
                }
                .frame(width: 40, height: 40)
                .entityAvatarShape(type)
            } else {
                initialCircle
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(safeName)
                    .font(AGTypography.base)
                    .fontWeight(.medium)
                    .foregroundStyle(Color.agText)
                Text(type.capitalized)
                    .font(AGTypography.xs)
                    .foregroundStyle(Color.agMuted)
            }

            Spacer()

            if let score = trustScore {
                TrustBadge(score: score)
            }
        }
    }

    private var initialCircle: some View {
        Group {
            if type == "agent" {
                AgentHexShape()
                    .fill(
                        LinearGradient(
                            colors: [.agPrimary, .agAccent],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 40, height: 40)
                    .overlay(
                        Text(String(safeName.prefix(1)).uppercased())
                            .font(AGTypography.sm)
                            .fontWeight(.bold)
                            .foregroundStyle(.white)
                    )
            } else {
                Circle()
                    .fill(
                        LinearGradient(
                            colors: [.agPrimary, .agAccent],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 40, height: 40)
                    .overlay(
                        Text(String(safeName.prefix(1)).uppercased())
                            .font(AGTypography.sm)
                            .fontWeight(.bold)
                            .foregroundStyle(.white)
                    )
            }
        }
    }
}
