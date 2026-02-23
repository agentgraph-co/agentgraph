// ForceGraphView — SwiftUI Canvas force-directed graph with semantic zoom
// Zoom spreads nodes apart but keeps circles/labels at readable screen-pixel sizes

import SwiftUI

struct ForceGraphView: View {
    let nodes: [ForceNode]
    let edges: [ForceEdge]
    var onNodeTap: ((String) -> Void)?
    var onNodeLongPress: ((String) -> Void)?
    var selectedNodeId: String?
    var layoutId: UUID

    // Zoom/pan state
    @State private var currentScale: CGFloat = 1.0
    @State private var baseScale: CGFloat = 1.0
    @State private var panOffset: CGSize = .zero
    @State private var basePanOffset: CGSize = .zero

    // Pre-computed node positions from force simulation (graph-space)
    @State private var positions: [String: CGPoint] = [:]
    @State private var lastLayoutId: UUID?

    var body: some View {
        GeometryReader { geo in
            Canvas { context, size in
                drawGraph(context: &context, size: size)
            }
            .contentShape(Rectangle())
            // Pinch to zoom (two fingers)
            .gesture(
                MagnifyGesture()
                    .onChanged { value in
                        currentScale = clampScale(baseScale * value.magnification)
                    }
                    .onEnded { _ in
                        baseScale = currentScale
                    }
            )
            // Drag to pan (one finger, requires movement)
            .simultaneousGesture(
                DragGesture(minimumDistance: 10)
                    .onChanged { value in
                        panOffset = CGSize(
                            width: basePanOffset.width + value.translation.width,
                            height: basePanOffset.height + value.translation.height
                        )
                    }
                    .onEnded { _ in
                        basePanOffset = panOffset
                    }
            )
            // Tap for node selection
            .onTapGesture { location in
                if let nodeId = hitTest(at: location, viewSize: geo.size) {
                    onNodeTap?(nodeId)
                }
            }
            .onChange(of: layoutId) { _, _ in
                computePositions(in: geo.size)
                lastLayoutId = layoutId
            }
            .onAppear {
                if positions.isEmpty || lastLayoutId != layoutId {
                    computePositions(in: geo.size)
                    lastLayoutId = layoutId
                }
            }
        }
    }

    private func clampScale(_ s: CGFloat) -> CGFloat {
        max(0.3, min(8.0, s))
    }

    // MARK: - Coordinate Transform (semantic zoom)

    /// Graph-space → Screen-space.
    /// Zoom spreads positions from view center; pan shifts in screen pixels.
    private func toScreen(_ graphPos: CGPoint, viewSize: CGSize) -> CGPoint {
        let cx = viewSize.width / 2
        let cy = viewSize.height / 2
        return CGPoint(
            x: (graphPos.x - cx) * currentScale + cx + panOffset.width,
            y: (graphPos.y - cy) * currentScale + cy + panOffset.height
        )
    }

    // MARK: - Hit Testing (screen-space)

    private func hitTest(at point: CGPoint, viewSize: CGSize) -> String? {
        let rScale = pow(currentScale, 0.2)
        for node in nodes.reversed() {
            guard let gPos = positions[node.id] else { continue }
            let sp = toScreen(gPos, viewSize: viewSize)
            let r = node.radius * rScale
            let dx = point.x - sp.x
            let dy = point.y - sp.y
            let tapR = max(r + 6, 22)
            if dx * dx + dy * dy <= tapR * tapR {
                return node.id
            }
        }
        return nil
    }

    // MARK: - Drawing

    private func drawGraph(context: inout GraphicsContext, size: CGSize) {
        // Mild node radius growth: pow(scale, 0.2)
        // At 2x zoom → 1.15x radius; at 4x zoom → 1.32x radius
        let rScale = pow(currentScale, 0.2)

        // Edges
        for edge in edges {
            guard let fromG = positions[edge.source],
                  let toG = positions[edge.target] else { continue }
            let from = toScreen(fromG, viewSize: size)
            let to = toScreen(toG, viewSize: size)

            var path = Path()
            path.move(to: from)
            path.addLine(to: to)
            context.stroke(
                path,
                with: .color(edgeColor(for: edge.edgeType).opacity(0.4)),
                lineWidth: edgeLineWidth(for: edge)
            )
        }

        // Nodes
        for node in nodes {
            guard let gPos = positions[node.id] else { continue }
            let sp = toScreen(gPos, viewSize: size)
            let r = node.radius * rScale
            let cc = ForceGraphViewModel.colorForCluster(node.clusterId)
            let color = Color(red: cc.red, green: cc.green, blue: cc.blue)

            // Glow ring
            let glowR = r * 1.8
            context.fill(
                Circle().path(in: CGRect(x: sp.x - glowR, y: sp.y - glowR,
                                         width: glowR * 2, height: glowR * 2)),
                with: .color(color.opacity(0.15))
            )

            // Node circle
            let nr = CGRect(x: sp.x - r, y: sp.y - r, width: r * 2, height: r * 2)
            context.fill(Circle().path(in: nr), with: .color(color))
            context.stroke(Circle().path(in: nr),
                           with: .color(color.opacity(0.7)),
                           lineWidth: node.isCenter ? 3 : 1.5)

            // Selection ring
            if node.id == selectedNodeId {
                let sr = r + 4
                let srr = CGRect(x: sp.x - sr, y: sp.y - sr, width: sr * 2, height: sr * 2)
                context.stroke(Circle().path(in: srr), with: .color(.white), lineWidth: 2)
            }

            // Icon letter
            let letter = node.type == "human" ? "H" : "A"
            context.draw(
                Text(letter)
                    .font(.system(size: min(r * 0.7, 14), weight: .bold))
                    .foregroundColor(.white),
                at: sp
            )

            // Label — visible at 0.5x and above
            if currentScale >= 0.5 {
                context.draw(
                    Text(node.label)
                        .font(.system(size: 11))
                        .foregroundColor(Color(red: 0.804, green: 0.839, blue: 0.957)),
                    at: CGPoint(x: sp.x, y: sp.y + r + 8)
                )
            }

            // Trust badge — visible when zoomed in
            if currentScale >= 1.5 {
                let pct = String(format: "%.0f%%", node.trustScore * 100)
                context.draw(
                    Text(pct)
                        .font(.system(size: 9))
                        .foregroundColor(Color(red: 0.424, green: 0.439, blue: 0.525)),
                    at: CGPoint(x: sp.x, y: sp.y - r - 6)
                )
            }
        }

        // Zoom indicator
        let zoomText = String(format: "%.1fx", currentScale)
        context.draw(
            Text(zoomText)
                .font(.system(size: 10))
                .foregroundColor(Color.white.opacity(0.3)),
            at: CGPoint(x: 30, y: size.height - 16)
        )
    }

    // MARK: - Force Simulation

    private func computePositions(in size: CGSize) {
        guard !nodes.isEmpty, size.width > 0, size.height > 0 else {
            positions = [:]
            return
        }

        var pos: [String: CGPoint] = [:]
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        let spread = min(size.width, size.height) * 0.35
        let count = nodes.count

        for (i, node) in nodes.enumerated() {
            if node.isCenter {
                pos[node.id] = center
            } else {
                let angle = CGFloat(i) * 2.0 * .pi / CGFloat(max(1, count - 1))
                let r = node.connections.count > 2
                    ? spread * 0.5
                    : spread * CGFloat.random(in: 0.6...0.9)
                pos[node.id] = CGPoint(x: center.x + cos(angle) * r,
                                       y: center.y + sin(angle) * r)
            }
        }

        let nodeIds = nodes.map { $0.id }

        for _ in 0..<80 {
            var forces: [String: CGVector] = [:]
            for nid in nodeIds { forces[nid] = .zero }

            // Repulsion
            for i in 0..<nodeIds.count {
                for j in (i + 1)..<nodeIds.count {
                    let a = nodeIds[i], b = nodeIds[j]
                    guard let pa = pos[a], let pb = pos[b] else { continue }
                    let dx = pb.x - pa.x
                    let dy = pb.y - pa.y
                    let distSq = max(dx * dx + dy * dy, 100)
                    let dist = sqrt(distSq)
                    let f: CGFloat = -50.0 / distSq
                    let fx = f * dx / dist
                    let fy = f * dy / dist
                    forces[a]!.dx += fx
                    forces[a]!.dy += fy
                    forces[b]!.dx -= fx
                    forces[b]!.dy -= fy
                }
            }

            // Springs
            for edge in edges {
                guard let pa = pos[edge.source], let pb = pos[edge.target] else { continue }
                let dx = pb.x - pa.x
                let dy = pb.y - pa.y
                let dist = max(sqrt(dx * dx + dy * dy), 1)
                let disp = dist - 120.0
                let fx = 0.05 * disp * dx / dist
                let fy = 0.05 * disp * dy / dist
                forces[edge.source]!.dx += fx
                forces[edge.source]!.dy += fy
                forces[edge.target]!.dx -= fx
                forces[edge.target]!.dy -= fy
            }

            // Gravity
            for nid in nodeIds {
                guard let p = pos[nid] else { continue }
                forces[nid]!.dx += (center.x - p.x) * 0.002
                forces[nid]!.dy += (center.y - p.y) * 0.002
            }

            // Apply
            for nid in nodeIds {
                guard var p = pos[nid], let f = forces[nid] else { continue }
                let mag = sqrt(f.dx * f.dx + f.dy * f.dy)
                let cap: CGFloat = 15
                let sc = mag > cap ? cap / mag : 1.0
                p.x += f.dx * sc
                p.y += f.dy * sc
                pos[nid] = p
            }
        }

        positions = pos
        currentScale = 1.0
        baseScale = 1.0
        panOffset = .zero
        basePanOffset = .zero
    }

    // MARK: - Styling

    private func edgeColor(for type: String) -> Color {
        switch type {
        case "follow": Color(red: 0.118, green: 0.200, blue: 0.200)
        case "attestation": Color(red: 0.651, green: 0.890, blue: 0.631)
        case "operator_agent": Color(red: 0.537, green: 0.706, blue: 0.980)
        case "collaboration": Color(red: 0.796, green: 0.651, blue: 0.969)
        case "service": Color(red: 0.980, green: 0.702, blue: 0.529)
        default: Color(red: 0.424, green: 0.439, blue: 0.525)
        }
    }

    private func edgeLineWidth(for edge: ForceEdge) -> CGFloat {
        switch edge.edgeType {
        case "attestation": CGFloat(1.0 + (edge.weight ?? 0.5) * 2.0)
        case "follow": 1.0
        default: 1.5
        }
    }
}
