// GraphView — Live 2D trust network visualization with pinch-to-zoom and pan

import SwiftUI

struct GraphView: View {
    @Environment(AuthViewModel.self) private var auth
    @State private var viewModel = GraphViewModel()

    // Gesture state
    @State private var scale: CGFloat = 1.0
    @State private var lastScale: CGFloat = 1.0
    @State private var offset: CGSize = .zero
    @State private var lastOffset: CGSize = .zero

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
                    // Zoomable/pannable graph container
                    graphContent
                        .scaleEffect(scale)
                        .offset(offset)
                        // #37: Use simultaneousGesture to prevent conflicts with nav taps
                        .simultaneousGesture(magnifyGesture)
                        .simultaneousGesture(dragGesture)
                        .gesture(doubleTapGesture)

                    // Stats overlay (fixed, not affected by zoom)
                    VStack {
                        // Zoom indicator
                        if scale != 1.0 {
                            HStack(spacing: AGSpacing.sm) {
                                Text(String(format: "%.0f%%", scale * 100))
                                    .font(AGTypography.xs)
                                    .foregroundStyle(Color.agMuted)
                                Button {
                                    withAnimation(.spring(duration: 0.3)) {
                                        scale = 1.0
                                        lastScale = 1.0
                                        offset = .zero
                                        lastOffset = .zero
                                    }
                                } label: {
                                    Image(systemName: "arrow.counterclockwise")
                                        .font(AGTypography.xs)
                                        .foregroundStyle(Color.agPrimary)
                                }
                            }
                            .padding(.horizontal, AGSpacing.md)
                            .padding(.vertical, AGSpacing.xs)
                            .glassCard(padding: AGSpacing.sm)
                            .padding(.top, AGSpacing.sm)
                        }

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
                                    let scores = viewModel.nodes.compactMap(\.trustScore)
                                    let avgTrust = scores.isEmpty ? 0 : scores.reduce(0, +) / Double(scores.count)
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
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Menu {
                        Button {
                            Task { await viewModel.loadGraph(centerId: auth.currentUser?.id) }
                        } label: {
                            Label("Reload", systemImage: "arrow.clockwise")
                        }
                        Button {
                            Task {
                                if let id = auth.currentUser?.id {
                                    await viewModel.loadGraph(centerId: id)
                                }
                            }
                        } label: {
                            Label("Center on Me", systemImage: "person.circle")
                        }
                        Button {
                            withAnimation(.spring(duration: 0.3)) {
                                scale = 1.0
                                lastScale = 1.0
                                offset = .zero
                                lastOffset = .zero
                            }
                        } label: {
                            Label("Reset View", systemImage: "arrow.counterclockwise")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                    .tint(.agPrimary)
                }
            }
            // Node ID is a String (lowercase UUID) — parse for profile navigation
            .navigationDestination(for: String.self) { nodeId in
                if let uuid = UUID(uuidString: nodeId) {
                    ProfileDetailView(entityId: uuid)
                }
            }
            .task {
                await viewModel.loadGraph(centerId: auth.currentUser?.id)
            }
        }
    }

    // MARK: - Graph Content

    private var graphContent: some View {
        ZStack {
            // #20: Build nodeMap for O(1) lookup in Canvas
            let nodeMap = Dictionary(uniqueKeysWithValues: viewModel.nodes.map { ($0.id, $0) })

            // Canvas for edges and nodes
            Canvas { context, size in
                let center = CGPoint(x: size.width / 2, y: size.height / 2)

                // Draw edges
                for (source, target) in viewModel.edges {
                    guard let sourceNode = nodeMap[source],
                          let targetNode = nodeMap[target] else {
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
                        VStack(spacing: 2) {
                            Circle()
                                .fill(Color.clear)
                                .frame(width: node.isCenter ? 44 : 32, height: node.isCenter ? 44 : 32)
                            Text(node.label)
                                .font(AGTypography.xs)
                                .foregroundStyle(
                                    // #36: selectedNode is String
                                    viewModel.selectedNode == node.id
                                        ? Color.agPrimary
                                        : Color.agMuted
                                )
                        }
                    }
                    .position(x: pos.x, y: pos.y + (node.isCenter ? 8 : 4))
                }
            }
        }
    }

    // MARK: - Gestures

    private var magnifyGesture: some Gesture {
        MagnifyGesture()
            .onChanged { value in
                let newScale = lastScale * value.magnification
                scale = min(max(newScale, 0.3), 5.0)
            }
            .onEnded { _ in
                lastScale = scale
            }
    }

    private var dragGesture: some Gesture {
        DragGesture()
            .onChanged { value in
                offset = CGSize(
                    width: lastOffset.width + value.translation.width,
                    height: lastOffset.height + value.translation.height
                )
            }
            .onEnded { _ in
                lastOffset = offset
            }
    }

    private var doubleTapGesture: some Gesture {
        TapGesture(count: 2)
            .onEnded {
                withAnimation(.spring(duration: 0.3)) {
                    if scale != 1.0 || offset != .zero {
                        // Reset to default
                        scale = 1.0
                        lastScale = 1.0
                        offset = .zero
                        lastOffset = .zero
                    } else {
                        // Zoom in 2x
                        scale = 2.0
                        lastScale = 2.0
                    }
                }
            }
    }

    // MARK: - Helpers

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
