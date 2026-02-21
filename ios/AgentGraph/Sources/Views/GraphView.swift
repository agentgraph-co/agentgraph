// GraphView — Live 2D trust network visualization from API

import SwiftUI

struct GraphView: View {
    @Environment(AuthViewModel.self) private var auth
    @State private var viewModel = GraphViewModel()

    var body: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                if viewModel.isLoading && viewModel.nodes.isEmpty {
                    LoadingStateView(state: .loading)
                } else if let error = viewModel.error, viewModel.nodes.isEmpty {
                    LoadingStateView(state: .error(message: error, retry: {
                        await viewModel.loadGraph(centerId: auth.currentUser?.id)
                    }))
                } else {
                    // Network visualization
                    Canvas { context, size in
                        let center = CGPoint(x: size.width / 2, y: size.height / 2)

                        // Draw edges
                        for (source, target) in viewModel.edges {
                            guard let sourceNode = viewModel.nodes.first(where: { $0.id == source }),
                                  let targetNode = viewModel.nodes.first(where: { $0.id == target }) else {
                                continue
                            }
                            let sourcePos = nodePosition(sourceNode, center: center, size: size)
                            let targetPos = nodePosition(targetNode, center: center, size: size)
                            var path = Path()
                            path.move(to: sourcePos)
                            path.addLine(to: targetPos)
                            context.stroke(
                                path,
                                with: .color(.agBorder.opacity(0.5)),
                                lineWidth: 1
                            )
                        }

                        // Draw nodes
                        for node in viewModel.nodes {
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

                    // Node labels overlay with tap targets
                    ForEach(viewModel.nodes) { node in
                        GeometryReader { geo in
                            let center = CGPoint(x: geo.size.width / 2, y: geo.size.height / 2)
                            let pos = nodePosition(node, center: center, size: geo.size)

                            NavigationLink(value: node.id) {
                                Text(node.label)
                                    .font(AGTypography.xs)
                                    .foregroundStyle(
                                        viewModel.selectedNode?.id == node.id
                                            ? Color.agPrimary
                                            : Color.agMuted
                                    )
                            }
                            .position(x: pos.x, y: pos.y + (node.isCenter ? 30 : 22))
                        }
                    }

                    // Stats overlay
                    VStack {
                        Spacer()
                        GlassCard {
                            HStack(spacing: AGSpacing.xl) {
                                VStack(spacing: 2) {
                                    Text("\(viewModel.nodeCount)")
                                        .font(AGTypography.lg)
                                        .fontWeight(.bold)
                                        .foregroundStyle(Color.agText)
                                    Text("Nodes")
                                        .font(AGTypography.xs)
                                        .foregroundStyle(Color.agMuted)
                                }
                                VStack(spacing: 2) {
                                    Text("\(viewModel.edgeCount)")
                                        .font(AGTypography.lg)
                                        .fontWeight(.bold)
                                        .foregroundStyle(Color.agText)
                                    Text("Edges")
                                        .font(AGTypography.xs)
                                        .foregroundStyle(Color.agMuted)
                                }
                                VStack(spacing: 2) {
                                    let avgTrust = viewModel.nodes.compactMap(\.trustScore).reduce(0, +)
                                        / max(1, Double(viewModel.nodes.compactMap(\.trustScore).count))
                                    Text(String(format: "%.2f", avgTrust))
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
            }
            .navigationTitle("Graph")
            .toolbarColorScheme(.dark, for: .navigationBar)
            .navigationDestination(for: UUID.self) { entityId in
                ProfileDetailView(entityId: entityId)
            }
            .task {
                await viewModel.loadGraph(centerId: auth.currentUser?.id)
            }
        }
    }

    private func nodePosition(_ node: LayoutNode, center: CGPoint, size: CGSize) -> CGPoint {
        if node.isCenter {
            return center
        }
        let scale = min(size.width, size.height) * 0.35
        return CGPoint(
            x: center.x + node.x * scale,
            y: center.y + node.y * scale
        )
    }

    private func nodeColor(_ node: LayoutNode) -> Color {
        if node.isCenter { return .agPrimary }
        let score = node.trustScore ?? 0
        if score >= 0.8 { return .agAccent }
        if score >= 0.5 { return .agWarning }
        return .agMuted
    }
}
