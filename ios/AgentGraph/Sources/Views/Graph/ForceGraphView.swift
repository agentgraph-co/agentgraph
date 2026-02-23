// ForceGraphView — SwiftUI Canvas force-directed graph with native zoom/pan
// Replaces SpriteKit to avoid coordinate system and gesture conflicts

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

    // Pre-computed node positions from force simulation
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
            .onChange(of: layoutId) { _, newId in
                computePositions(in: geo.size)
                lastLayoutId = newId
            }
            .onAppear {
                if positions.isEmpty || lastLayoutId != layoutId {
                    computePositions(in: geo.size)
                    lastLayoutId = layoutId
                }
            }
        }
    }

    // MARK: - Gestures

    private var pinchGesture: some Gesture {
        MagnifyGesture()
            .onChanged { value in
                currentScale = max(0.3, min(5.0, baseScale * value.magnification))
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

    // MARK: - Hit Testing

    private func hitTest(at point: CGPoint, viewSize: CGSize) -> String? {
        // Reverse the Canvas transform to get graph coordinates
        let gx = (point.x - viewSize.width / 2) / currentScale - currentOffset.x + viewSize.width / 2
        let gy = (point.y - viewSize.height / 2) / currentScale - currentOffset.y + viewSize.height / 2

        // Check nodes in reverse order (top-most first)
        for node in nodes.reversed() {
            guard let pos = positions[node.id] else { continue }
            let dx = pos.x - gx
            let dy = pos.y - gy
            let tapRadius = max(node.radius + 6, 20) // minimum 20pt tap target
            if dx * dx + dy * dy <= tapRadius * tapRadius {
                return node.id
            }
        }
        return nil
    }

    // MARK: - Drawing

    private func drawGraph(context: inout GraphicsContext, size: CGSize) {
        // Apply zoom/pan transform
        context.translateBy(x: size.width / 2, y: size.height / 2)
        context.scaleBy(x: currentScale, y: currentScale)
        context.translateBy(x: currentOffset.x, y: currentOffset.y)
        context.translateBy(x: -size.width / 2, y: -size.height / 2)

        // Draw edges
        for edge in edges {
            guard let from = positions[edge.source],
                  let to = positions[edge.target] else { continue }
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
            guard let pos = positions[node.id] else { continue }
            let r = node.radius
            let cc = ForceGraphViewModel.colorForCluster(node.clusterId)
            let color = Color(red: cc.red, green: cc.green, blue: cc.blue)

            // Glow ring
            let glowR = r * 1.8
            context.fill(
                Circle().path(in: CGRect(x: pos.x - glowR, y: pos.y - glowR, width: glowR * 2, height: glowR * 2)),
                with: .color(color.opacity(0.15))
            )

            // Node circle
            let nodeRect = CGRect(x: pos.x - r, y: pos.y - r, width: r * 2, height: r * 2)
            context.fill(Circle().path(in: nodeRect), with: .color(color))
            context.stroke(
                Circle().path(in: nodeRect),
                with: .color(color.opacity(0.7)),
                lineWidth: node.isCenter ? 3 : 1.5
            )

            // Selection ring
            if node.id == selectedNodeId {
                let ringR = r + 4
                let ringRect = CGRect(x: pos.x - ringR, y: pos.y - ringR, width: ringR * 2, height: ringR * 2)
                context.stroke(Circle().path(in: ringRect), with: .color(.white), lineWidth: 2)
            }

            // Icon letter (H/A)
            let letter = node.type == "human" ? "H" : "A"
            context.draw(
                Text(letter)
                    .font(.system(size: r * 0.7, weight: .bold))
                    .foregroundColor(.white),
                at: pos
            )

            // Label — show at normal zoom and above
            if currentScale >= 0.7 {
                context.draw(
                    Text(node.label)
                        .font(.system(size: 11))
                        .foregroundColor(Color(red: 0.804, green: 0.839, blue: 0.957)),
                    at: CGPoint(x: pos.x, y: pos.y + r + 10)
                )
            }

            // Trust score badge — show when zoomed in
            if currentScale >= 1.8 {
                let trustText = String(format: "%.0f%%", node.trustScore * 100)
                context.draw(
                    Text(trustText)
                        .font(.system(size: 9))
                        .foregroundColor(Color(red: 0.424, green: 0.439, blue: 0.525)),
                    at: CGPoint(x: pos.x, y: pos.y - r - 8)
                )
            }
        }
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
                pos[node.id] = CGPoint(x: center.x + cos(angle) * r, y: center.y + sin(angle) * r)
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
