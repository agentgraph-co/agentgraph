// GraphNodeView — SwiftUI node component for graph overlays and detail panels

import SwiftUI

/// A SwiftUI view representing a single graph node, used in overlay panels.
struct GraphNodeView: View {
    let node: ForceNode
    let isSelected: Bool
    var onTap: (() -> Void)?

    var body: some View {
        Button(action: { onTap?() }) {
            HStack(spacing: AGSpacing.md) {
                // Node circle with cluster color
                ZStack {
                    Circle()
                        .fill(nodeColor.opacity(0.2))
                        .frame(width: circleSize + 8, height: circleSize + 8)

                    Circle()
                        .fill(nodeColor)
                        .frame(width: circleSize, height: circleSize)

                    Image(systemName: node.type == "human" ? "person.fill" : "cpu")
                        .font(.system(size: circleSize * 0.4))
                        .foregroundStyle(.white)
                }

                VStack(alignment: .leading, spacing: 2) {
                    Text(node.label)
                        .font(AGTypography.sm)
                        .fontWeight(.medium)
                        .foregroundStyle(isSelected ? Color.agPrimary : Color.agText)
                        .lineLimit(1)

                    HStack(spacing: AGSpacing.sm) {
                        // Trust score badge
                        Text(String(format: "%.2f", node.trustScore))
                            .font(AGTypography.xs)
                            .foregroundStyle(trustColor)

                        // Type badge
                        Text(node.type.capitalized)
                            .font(AGTypography.xs)
                            .foregroundStyle(Color.agMuted)

                        // Connection count
                        HStack(spacing: 2) {
                            Image(systemName: "link")
                                .font(.system(size: 9))
                            Text("\(node.connections.count)")
                                .font(AGTypography.xs)
                        }
                        .foregroundStyle(Color.agMuted)
                    }
                }

                Spacer()

                if isSelected {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(Color.agPrimary)
                }
            }
            .padding(AGSpacing.md)
            .background(
                RoundedRectangle(cornerRadius: AGRadii.lg)
                    .fill(isSelected ? Color.agSurfaceElevated : Color.agSurface)
                    .overlay(
                        RoundedRectangle(cornerRadius: AGRadii.lg)
                            .strokeBorder(
                                isSelected ? Color.agPrimary.opacity(0.5) : Color.agBorder.opacity(0.3),
                                lineWidth: 1
                            )
                    )
            )
        }
        .buttonStyle(.plain)
    }

    private var circleSize: CGFloat {
        CGFloat(16 + node.trustScore * 16)
    }

    private var nodeColor: Color {
        let c = ForceGraphViewModel.colorForCluster(node.clusterId)
        return Color(red: c.red, green: c.green, blue: c.blue)
    }

    private var trustColor: Color {
        if node.trustScore >= 0.8 { return .agSuccess }
        if node.trustScore >= 0.5 { return .agWarning }
        return .agDanger
    }
}

// MARK: - Compact Variant

/// A minimal circle-only node view for inline usage (e.g., trust flow path).
struct GraphNodeCircle: View {
    let label: String
    let type: String
    let trustScore: Double
    let clusterId: Int?
    let size: CGFloat

    var body: some View {
        VStack(spacing: 2) {
            ZStack {
                Circle()
                    .fill(nodeColor.opacity(0.2))
                    .frame(width: size + 6, height: size + 6)

                Circle()
                    .fill(nodeColor)
                    .frame(width: size, height: size)

                Image(systemName: type == "human" ? "person.fill" : "cpu")
                    .font(.system(size: size * 0.35))
                    .foregroundStyle(.white)
            }

            Text(label)
                .font(AGTypography.xs)
                .foregroundStyle(Color.agText)
                .lineLimit(1)
                .frame(maxWidth: size * 2.5)
        }
    }

    private var nodeColor: Color {
        let c = ForceGraphViewModel.colorForCluster(clusterId)
        return Color(red: c.red, green: c.green, blue: c.blue)
    }
}
