// GraphView — Simplified 2D trust network visualization

import SwiftUI

struct GraphView: View {
    @State private var nodes: [GraphNode] = GraphNode.sample
    @State private var selectedNode: GraphNode?

    var body: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                // Network visualization
                Canvas { context, size in
                    let center = CGPoint(x: size.width / 2, y: size.height / 2)

                    // Draw edges
                    for node in nodes {
                        let pos = nodePosition(node, center: center, size: size)
                        for connIdx in node.connections {
                            if let connected = nodes.first(where: { $0.id == connIdx }) {
                                let connPos = nodePosition(connected, center: center, size: size)
                                var path = Path()
                                path.move(to: pos)
                                path.addLine(to: connPos)
                                context.stroke(
                                    path,
                                    with: .color(.agBorder.opacity(0.5)),
                                    lineWidth: 1
                                )
                            }
                        }
                    }

                    // Draw nodes
                    for node in nodes {
                        let pos = nodePosition(node, center: center, size: size)
                        let radius = node.isCenter ? 20.0 : 12.0

                        // Glow
                        let glowRect = CGRect(
                            x: pos.x - radius * 1.5,
                            y: pos.y - radius * 1.5,
                            width: radius * 3,
                            height: radius * 3
                        )
                        context.fill(
                            Circle().path(in: glowRect),
                            with: .color(nodeColor(node).opacity(0.2))
                        )

                        // Node circle
                        let nodeRect = CGRect(
                            x: pos.x - radius,
                            y: pos.y - radius,
                            width: radius * 2,
                            height: radius * 2
                        )
                        context.fill(
                            Circle().path(in: nodeRect),
                            with: .color(nodeColor(node))
                        )
                    }
                }

                // Node labels overlay
                ForEach(nodes) { node in
                    GeometryReader { geo in
                        let center = CGPoint(x: geo.size.width / 2, y: geo.size.height / 2)
                        let pos = nodePosition(node, center: center, size: geo.size)

                        Text(node.label)
                            .font(AGTypography.xs)
                            .foregroundStyle(Color.agMuted)
                            .position(x: pos.x, y: pos.y + (node.isCenter ? 30 : 22))
                    }
                }

                // Stats overlay
                VStack {
                    Spacer()
                    GlassCard {
                        HStack(spacing: AGSpacing.xl) {
                            VStack(spacing: 2) {
                                Text("\(nodes.count)")
                                    .font(AGTypography.lg)
                                    .fontWeight(.bold)
                                    .foregroundStyle(Color.agText)
                                Text("Nodes")
                                    .font(AGTypography.xs)
                                    .foregroundStyle(Color.agMuted)
                            }
                            VStack(spacing: 2) {
                                let edgeCount = nodes.reduce(0) { $0 + $1.connections.count } / 2
                                Text("\(edgeCount)")
                                    .font(AGTypography.lg)
                                    .fontWeight(.bold)
                                    .foregroundStyle(Color.agText)
                                Text("Edges")
                                    .font(AGTypography.xs)
                                    .foregroundStyle(Color.agMuted)
                            }
                            VStack(spacing: 2) {
                                Text("0.87")
                                    .font(AGTypography.lg)
                                    .fontWeight(.bold)
                                    .foregroundStyle(Color.agSuccess)
                                Text("Avg Trust")
                                    .font(AGTypography.xs)
                                    .foregroundStyle(Color.agMuted)
                            }
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .padding(.horizontal, AGSpacing.base)
                    .padding(.bottom, AGSpacing.sm)
                }
            }
            .navigationTitle("Graph")
            .toolbarColorScheme(.dark, for: .navigationBar)
        }
    }

    private func nodePosition(_ node: GraphNode, center: CGPoint, size: CGSize) -> CGPoint {
        if node.isCenter {
            return center
        }
        let scale = min(size.width, size.height) * 0.35
        return CGPoint(
            x: center.x + node.x * scale,
            y: center.y + node.y * scale
        )
    }

    private func nodeColor(_ node: GraphNode) -> Color {
        if node.isCenter { return .agPrimary }
        if node.trustScore >= 0.8 { return .agAccent }
        if node.trustScore >= 0.5 { return .agWarning }
        return .agMuted
    }
}

// MARK: - Graph Node Model

struct GraphNode: Identifiable {
    let id: Int
    let label: String
    let x: Double
    let y: Double
    let trustScore: Double
    let isCenter: Bool
    let connections: [Int]

    static let sample: [GraphNode] = [
        GraphNode(id: 0, label: "You", x: 0, y: 0, trustScore: 0.95, isCenter: true, connections: [1, 2, 3, 4, 5]),
        GraphNode(id: 1, label: "agent-alpha", x: -0.6, y: -0.7, trustScore: 0.87, isCenter: false, connections: [0, 2, 4]),
        GraphNode(id: 2, label: "researcher-9", x: 0.7, y: -0.5, trustScore: 0.92, isCenter: false, connections: [0, 1, 3]),
        GraphNode(id: 3, label: "builder-x", x: 0.8, y: 0.4, trustScore: 0.78, isCenter: false, connections: [0, 2, 5]),
        GraphNode(id: 4, label: "analyst-3", x: -0.5, y: 0.6, trustScore: 0.85, isCenter: false, connections: [0, 1]),
        GraphNode(id: 5, label: "human.kenne", x: 0.0, y: 0.8, trustScore: 0.95, isCenter: false, connections: [0, 3]),
    ]
}
