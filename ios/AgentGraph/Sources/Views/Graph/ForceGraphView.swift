// ForceGraphView — SwiftUI Canvas force-directed graph with semantic zoom
// Zoom spreads nodes apart but keeps circles/labels at readable screen-pixel sizes
// (like react-force-graph-2d on the web, not "picture zoom")

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
    @State private var currentOffset: CGPoint = .zero
    @State private var baseOffset: CGPoint = .zero

    // Touch tracking for tap vs long-press vs drag
    @State private var touchDown: Date?
    @State private var isDragging = false

    // Pre-computed node positions from force simulation (graph-space)
    @State private var positions: [String: CGPoint] = [:]
    @State private var lastLayoutId: UUID?

    var body: some View {
        GeometryReader { geo in
            Canvas { context, size in
                drawGraph(context: &context, size: size)
            }
            .contentShape(Rectangle())
            .gesture(dragGesture(viewSize: geo.size))
            .simultaneousGesture(pinchGesture)
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

    // MARK: - Coordinate Transform

    /// Convert graph-space position to screen-space position.
    /// Zoom spreads positions apart from center; pan shifts everything.
    private func toScreen(_ graphPos: CGPoint, viewSize: CGSize) -> CGPoint {
        let cx = viewSize.width / 2
        let cy = viewSize.height / 2
        return CGPoint(
            x: (graphPos.x - cx + currentOffset.x) * currentScale + cx,
            y: (graphPos.y - cy + currentOffset.y) * currentScale + cy
        )
    }

    /// Convert screen-space tap point back to graph-space.
    private func toGraph(_ screenPos: CGPoint, viewSize: CGSize) -> CGPoint {
        let cx = viewSize.width / 2
        let cy = viewSize.height / 2
        return CGPoint(
            x: (screenPos.x - cx) / currentScale - currentOffset.x + cx,
            y: (screenPos.y - cy) / currentScale - currentOffset.y + cy
        )
    }

    // MARK: - Gestures

    private var pinchGesture: some Gesture {
        MagnifyGesture()
            .onChanged { value in
                currentScale = max(0.3, min(8.0, baseScale * value.magnification))
            }
            .onEnded { _ in
                baseScale = currentScale
            }
    }

    private func dragGesture(viewSize: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 0)
            .onChanged { value in
                if touchDown == nil {
                    touchDown = Date()
                }
                let movedX = abs(value.translation.width)
                let movedY = abs(value.translation.height)
                if movedX > 8 || movedY > 8 {
                    isDragging = true
                    // Offset is in graph-space; divide screen drag by scale
                    currentOffset = CGPoint(
                        x: baseOffset.x + value.translation.width / currentScale,
                        y: baseOffset.y + value.translation.height / currentScale
                    )
                }
            }
            .onEnded { value in
                if isDragging {
                    baseOffset = currentOffset
                } else {
                    let duration = Date().timeIntervalSince(touchDown ?? Date())
                    if let nodeId = hitTest(at: value.location, viewSize: viewSize) {
                        if duration >= 0.5 {
                            onNodeLongPress?(nodeId)
                        } else {
                            onNodeTap?(nodeId)
                        }
                    }
                }
                isDragging = false
                touchDown = nil
            }
    }

    // MARK: - Hit Testing (screen-space)

    private func hitTest(at point: CGPoint, viewSize: CGSize) -> String? {
        // Mild radius growth so tap targets scale with zoom (but much less than 1:1)
        let rScale = pow(currentScale, 0.2)

        for node in nodes.reversed() {
            guard let gPos = positions[node.id] else { continue }
            let sp = toScreen(gPos, viewSize: viewSize)
            let r = node.radius * rScale
            let dx = point.x - sp.x
            let dy = point.y - sp.y
            let tapR = max(r + 6, 22) // generous tap target
            if dx * dx + dy * dy <= tapR * tapR {
                return node.id
            }
        }
        return nil
    }

    // MARK: - Drawing (semantic zoom — positions transform, sizes stay fixed)

    private func drawGraph(context: inout GraphicsContext, size: CGSize) {
        // How much node radius grows with zoom: very mild (exponent 0.2)
        // At 2x zoom → radius is ~1.15x; at 4x zoom → radius is ~1.32x
        let rScale = pow(currentScale, 0.2)

        // Draw edges first (below nodes)
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
                with: .color(edgeSwiftColor(for: edge.edgeType).opacity(0.4)),
                lineWidth: edgeWidth(for: edge)
            )
        }

        // Draw nodes
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
            let nodeRect = CGRect(x: sp.x - r, y: sp.y - r, width: r * 2, height: r * 2)
            context.fill(Circle().path(in: nodeRect), with: .color(color))
            context.stroke(
                Circle().path(in: nodeRect),
                with: .color(color.opacity(0.7)),
                lineWidth: node.isCenter ? 3 : 1.5
            )

            // Selection ring
            if node.id == selectedNodeId {
                let ringR = r + 4
                let ringRect = CGRect(x: sp.x - ringR, y: sp.y - ringR,
                                      width: ringR * 2, height: ringR * 2)
                context.stroke(Circle().path(in: ringRect), with: .color(.white), lineWidth: 2)
            }

            // Icon letter (H/A) — fixed screen-pixel font size
            let letter = node.type == "human" ? "H" : "A"
            context.draw(
                Text(letter)
                    .font(.system(size: min(r * 0.7, 14), weight: .bold))
                    .foregroundColor(.white),
                at: sp
            )

            // Label — always visible at 1x, fades at extreme zoom-out
            if currentScale >= 0.5 {
                context.draw(
                    Text(node.label)
                        .font(.system(size: 11))
                        .foregroundColor(Color(red: 0.804, green: 0.839, blue: 0.957)),
                    at: CGPoint(x: sp.x, y: sp.y + r + 8)
                )
            }

            // Trust score badge — appears when zoomed in past 1.5x
            if currentScale >= 1.5 {
                let trustText = String(format: "%.0f%%", node.trustScore * 100)
                context.draw(
                    Text(trustText)
                        .font(.system(size: 9))
                        .foregroundColor(Color(red: 0.424, green: 0.439, blue: 0.525)),
                    at: CGPoint(x: sp.x, y: sp.y - r - 6)
                )
            }
        }

        // Zoom level indicator (bottom-left, fixed screen position)
        context.draw(
            Text(String(format: "%.1fx", currentScale))
                .font(.system(size: 10))
                .foregroundColor(Color(red: 0.424, green: 0.439, blue: 0.525, opacity: 0.6)),
            at: CGPoint(x: 32, y: size.height - 16)
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

        // Initial circular layout
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

        let nodeIds = nodes.map(\.id)

        // Run force simulation (80 iterations)
        for _ in 0..<80 {
            var forces: [String: CGVector] = [:]
            for nid in nodeIds { forces[nid] = .zero }

            // Repulsion between all node pairs
            for i in 0..<nodeIds.count {
                for j in (i + 1)..<nodeIds.count {
                    let a = nodeIds[i], b = nodeIds[j]
                    guard let pa = pos[a], let pb = pos[b] else { continue }
                    let dx = pb.x - pa.x
                    let dy = pb.y - pa.y
                    let distSq = max(dx * dx + dy * dy, 100)
                    let dist = sqrt(distSq)
                    let f: CGFloat = -50.0 / distSq
                    let fx = f * dx / dist, fy = f * dy / dist
                    forces[a]!.dx += fx; forces[a]!.dy += fy
                    forces[b]!.dx -= fx; forces[b]!.dy -= fy
                }
            }

            // Spring forces along edges
            for edge in edges {
                guard let pa = pos[edge.source], let pb = pos[edge.target] else { continue }
                let dx = pb.x - pa.x
                let dy = pb.y - pa.y
                let dist = max(sqrt(dx * dx + dy * dy), 1)
                let disp = dist - 120.0
                let fx = 0.05 * disp * dx / dist, fy = 0.05 * disp * dy / dist
                forces[edge.source]!.dx += fx; forces[edge.source]!.dy += fy
                forces[edge.target]!.dx -= fx; forces[edge.target]!.dy -= fy
            }

            // Gravity toward center
            for nid in nodeIds {
                guard let p = pos[nid] else { continue }
                forces[nid]!.dx += (center.x - p.x) * 0.002
                forces[nid]!.dy += (center.y - p.y) * 0.002
            }

            // Apply forces with velocity cap
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

        // Reset zoom/pan to show full graph
        currentScale = 1.0
        baseScale = 1.0
        currentOffset = .zero
        baseOffset = .zero
    }

    // MARK: - Styling

    private func edgeSwiftColor(for type: String) -> Color {
        switch type {
        case "follow": Color(red: 0.118, green: 0.200, blue: 0.200)
        case "attestation": Color(red: 0.651, green: 0.890, blue: 0.631)
        case "operator_agent": Color(red: 0.537, green: 0.706, blue: 0.980)
        case "collaboration": Color(red: 0.796, green: 0.651, blue: 0.969)
        case "service": Color(red: 0.980, green: 0.702, blue: 0.529)
        default: Color(red: 0.424, green: 0.439, blue: 0.525)
        }
    }

    private func edgeWidth(for edge: ForceEdge) -> CGFloat {
        switch edge.edgeType {
        case "attestation": CGFloat(1.0 + (edge.weight ?? 0.5) * 2.0)
        case "follow": 1.0
        default: 1.5
        }
    }
}
