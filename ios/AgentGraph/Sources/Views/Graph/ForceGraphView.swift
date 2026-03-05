// ForceGraphView — SwiftUI Canvas force-directed graph with semantic zoom
// Zoom spreads nodes apart but keeps circles/labels at readable screen-pixel sizes
// Animated directional particles flow along edges (like react-force-graph on web)
//
// Optimizations (#136):
// - Viewport culling: skip drawing off-screen nodes/edges
// - Barnes-Hut quadtree: O(n²) → O(n log n) repulsive force computation
// - Adaptive LOD: fewer particles/glow at low zoom, skip labels for dense graphs
// - Adaptive iteration count: scale simulation effort with node count
// - Reduced per-frame allocations: pre-compute edge colors, reuse paths

import SwiftUI

// MARK: - Barnes-Hut Quadtree

/// Quadtree node for Barnes-Hut force approximation.
/// Groups distant nodes into a single center-of-mass for O(n log n) repulsion.
private final class QuadTreeNode {
    var bounds: CGRect
    var centerOfMass: CGPoint = .zero
    var totalMass: CGFloat = 0
    var children: [QuadTreeNode?] = [nil, nil, nil, nil] // NW, NE, SW, SE
    var bodyPosition: CGPoint? // Leaf node position (if exactly one body)
    var bodyIndex: Int = -1

    init(bounds: CGRect) {
        self.bounds = bounds
    }

    var isLeaf: Bool { bodyPosition != nil && totalMass <= 1 }
    var isEmpty: Bool { totalMass == 0 }

    func insert(position: CGPoint, index: Int) {
        if isEmpty {
            // Empty node — store body directly
            bodyPosition = position
            bodyIndex = index
            centerOfMass = position
            totalMass = 1
            return
        }

        if isLeaf {
            // Already has one body — subdivide
            let existingPos = bodyPosition!
            let existingIdx = bodyIndex
            bodyPosition = nil
            bodyIndex = -1

            insertIntoChild(position: existingPos, index: existingIdx)
            insertIntoChild(position: position, index: index)
        } else {
            insertIntoChild(position: position, index: index)
        }

        // Update center of mass
        let newMass = totalMass + 1
        centerOfMass = CGPoint(
            x: (centerOfMass.x * totalMass + position.x) / newMass,
            y: (centerOfMass.y * totalMass + position.y) / newMass
        )
        totalMass = newMass
    }

    private func insertIntoChild(position: CGPoint, index: Int) {
        let midX = bounds.midX
        let midY = bounds.midY
        let quadrant: Int
        if position.x <= midX {
            quadrant = position.y <= midY ? 0 : 2 // NW or SW
        } else {
            quadrant = position.y <= midY ? 1 : 3 // NE or SE
        }

        if children[quadrant] == nil {
            let childBounds: CGRect
            switch quadrant {
            case 0: childBounds = CGRect(x: bounds.minX, y: bounds.minY,
                                         width: bounds.width / 2, height: bounds.height / 2)
            case 1: childBounds = CGRect(x: midX, y: bounds.minY,
                                         width: bounds.width / 2, height: bounds.height / 2)
            case 2: childBounds = CGRect(x: bounds.minX, y: midY,
                                         width: bounds.width / 2, height: bounds.height / 2)
            default: childBounds = CGRect(x: midX, y: midY,
                                          width: bounds.width / 2, height: bounds.height / 2)
            }
            children[quadrant] = QuadTreeNode(bounds: childBounds)
        }

        children[quadrant]!.insert(position: position, index: index)
    }

    /// Barnes-Hut force calculation. theta controls accuracy (lower = more accurate).
    func calculateForce(on position: CGPoint, theta: CGFloat = 0.8,
                        fx: inout CGFloat, fy: inout CGFloat) {
        if isEmpty { return }

        let dx = centerOfMass.x - position.x
        let dy = centerOfMass.y - position.y
        let distSq = max(dx * dx + dy * dy, 100)

        if isLeaf {
            // Single body — compute exact force
            if distSq > 100 { // Skip self
                let dist = sqrt(distSq)
                let f: CGFloat = -50.0 / distSq
                fx += f * dx / dist
                fy += f * dy / dist
            }
            return
        }

        let size = bounds.width
        // If node is far enough away, treat as single body
        if size * size / distSq < theta * theta {
            let dist = sqrt(distSq)
            let f: CGFloat = -50.0 * totalMass / distSq
            fx += f * dx / dist
            fy += f * dy / dist
            return
        }

        // Otherwise recurse into children
        for child in children {
            child?.calculateForce(on: position, theta: theta, fx: &fx, fy: &fy)
        }
    }
}

// MARK: - ForceGraphView

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

    // Node dragging state
    @State private var draggedNodeId: String?
    @State private var dragStartedOnNode = false

    // Particle config per edge type
    private static let particleCounts: [String: Int] = [
        "attestation": 3,
        "operator_agent": 2,
        "collaboration": 2,
        "service": 2,
        "follow": 1,
    ]
    private static let particleSpeed: Double = 0.3

    // Pre-computed edge colors (avoid Color allocation per frame)
    private static let edgeColorMap: [String: (r: Double, g: Double, b: Double)] = [
        "follow": (0.118, 0.200, 0.200),
        "attestation": (0.651, 0.890, 0.631),
        "operator_agent": (0.537, 0.706, 0.980),
        "collaboration": (0.796, 0.651, 0.969),
        "service": (0.980, 0.702, 0.529),
    ]
    private static let defaultEdgeColor: (r: Double, g: Double, b: Double) = (0.424, 0.439, 0.525)

    var body: some View {
        GeometryReader { geo in
            TimelineView(.animation) { timeline in
                let time = timeline.date.timeIntervalSinceReferenceDate

                Canvas { context, size in
                    drawGraph(context: &context, size: size, time: time)
                }
                .contentShape(Rectangle())
            }
            .gesture(
                MagnifyGesture()
                    .onChanged { value in
                        currentScale = clampScale(baseScale * value.magnification)
                    }
                    .onEnded { _ in
                        baseScale = currentScale
                    }
            )
            .simultaneousGesture(
                DragGesture(minimumDistance: 6)
                    .onChanged { value in
                        if draggedNodeId == nil && !dragStartedOnNode {
                            if let nodeId = hitTest(at: value.startLocation, viewSize: geo.size) {
                                draggedNodeId = nodeId
                                dragStartedOnNode = true
                            } else {
                                dragStartedOnNode = false
                            }
                        }

                        if let nodeId = draggedNodeId {
                            positions[nodeId] = toGraph(value.location, viewSize: geo.size)
                        } else {
                            panOffset = CGSize(
                                width: basePanOffset.width + value.translation.width,
                                height: basePanOffset.height + value.translation.height
                            )
                        }
                    }
                    .onEnded { _ in
                        if draggedNodeId == nil {
                            basePanOffset = panOffset
                        }
                        draggedNodeId = nil
                        dragStartedOnNode = false
                    }
            )
            .gesture(
                LongPressGesture(minimumDuration: 0.5)
                    .sequenced(before: DragGesture(minimumDistance: 0))
                    .onEnded { value in
                        switch value {
                        case .second(true, let drag):
                            if let location = drag?.location,
                               let nodeId = hitTest(at: location, viewSize: geo.size) {
                                onNodeLongPress?(nodeId)
                            }
                        default:
                            break
                        }
                    }
            )
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

    private func toScreen(_ graphPos: CGPoint, viewSize: CGSize) -> CGPoint {
        let cx = viewSize.width / 2
        let cy = viewSize.height / 2
        return CGPoint(
            x: (graphPos.x - cx) * currentScale + cx + panOffset.width,
            y: (graphPos.y - cy) * currentScale + cy + panOffset.height
        )
    }

    private func toGraph(_ screenPos: CGPoint, viewSize: CGSize) -> CGPoint {
        let cx = viewSize.width / 2
        let cy = viewSize.height / 2
        return CGPoint(
            x: (screenPos.x - cx - panOffset.width) / currentScale + cx,
            y: (screenPos.y - cy - panOffset.height) / currentScale + cy
        )
    }

    // MARK: - Viewport Culling

    /// Returns the visible rect in screen-space with padding for nodes near edges.
    private func visibleRect(size: CGSize) -> CGRect {
        let padding: CGFloat = 60 // account for glow/label overflow
        return CGRect(x: -padding, y: -padding,
                      width: size.width + padding * 2,
                      height: size.height + padding * 2)
    }

    /// Quick check if a screen-space point is within the visible viewport.
    @inline(__always)
    private func isVisible(_ screenPoint: CGPoint, viewport: CGRect) -> Bool {
        viewport.contains(screenPoint)
    }

    /// Check if a line segment (edge) intersects the visible viewport.
    /// Uses a fast AABB overlap test on the edge bounding box.
    @inline(__always)
    private func isEdgeVisible(_ from: CGPoint, _ to: CGPoint, viewport: CGRect) -> Bool {
        let minX = min(from.x, to.x)
        let maxX = max(from.x, to.x)
        let minY = min(from.y, to.y)
        let maxY = max(from.y, to.y)
        return maxX >= viewport.minX && minX <= viewport.maxX
            && maxY >= viewport.minY && minY <= viewport.maxY
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

    // MARK: - Drawing (with viewport culling + adaptive LOD)

    private func drawGraph(context: inout GraphicsContext, size: CGSize, time: Double) {
        let rScale = pow(currentScale, 0.2)
        let viewport = visibleRect(size: size)
        let nodeCount = nodes.count

        // Adaptive LOD thresholds
        let showGlow = nodeCount < 200 || currentScale > 0.8
        let showParticles = nodeCount < 300 || currentScale > 0.6
        let showLabels = currentScale >= 0.5 && (nodeCount < 400 || currentScale > 1.0)
        let showTrustBadges = currentScale >= 1.5

        // Reduce particle count for large graphs
        let particleScale: Int = nodeCount > 200 ? 2 : 1

        // Edges + animated particles
        for edge in edges {
            guard let fromG = positions[edge.source],
                  let toG = positions[edge.target] else { continue }
            let from = toScreen(fromG, viewSize: size)
            let to = toScreen(toG, viewSize: size)

            // Viewport culling — skip edges entirely off-screen
            guard isEdgeVisible(from, to, viewport: viewport) else { continue }

            let ec = Self.edgeColorMap[edge.edgeType] ?? Self.defaultEdgeColor
            let color = Color(red: ec.r, green: ec.g, blue: ec.b)

            // Edge line
            var path = Path()
            path.move(to: from)
            path.addLine(to: to)
            context.stroke(path, with: .color(color.opacity(0.35)),
                           lineWidth: edgeLineWidth(for: edge))

            // Directional particles (LOD: skip when zoomed out on large graphs)
            if showParticles {
                let baseCount = Self.particleCounts[edge.edgeType] ?? 1
                let count = max(1, baseCount / particleScale)
                let particleR: CGFloat = 2.0
                for i in 0..<count {
                    let phase = Double(i) / Double(count)
                    let t = (time * Self.particleSpeed + phase)
                        .truncatingRemainder(dividingBy: 1.0)
                    let px = from.x + (to.x - from.x) * t
                    let py = from.y + (to.y - from.y) * t
                    let rect = CGRect(x: px - particleR, y: py - particleR,
                                      width: particleR * 2, height: particleR * 2)
                    context.fill(Circle().path(in: rect),
                                 with: .color(color.opacity(0.8)))
                }
            }
        }

        // Nodes
        for node in nodes {
            guard let gPos = positions[node.id] else { continue }
            let sp = toScreen(gPos, viewSize: size)

            // Viewport culling — skip nodes off-screen
            guard isVisible(sp, viewport: viewport) else { continue }

            let r = node.radius * rScale
            let cc = ForceGraphViewModel.colorForCluster(node.clusterId)
            let color = Color(red: cc.red, green: cc.green, blue: cc.blue)

            // Glow ring (LOD: skip for dense graphs at low zoom)
            if showGlow {
                let glowR = r * 1.8
                context.fill(
                    Circle().path(in: CGRect(x: sp.x - glowR, y: sp.y - glowR,
                                             width: glowR * 2, height: glowR * 2)),
                    with: .color(color.opacity(0.15))
                )
            }

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

            // Drag highlight ring
            if node.id == draggedNodeId {
                let dr = r + 6
                let drr = CGRect(x: sp.x - dr, y: sp.y - dr, width: dr * 2, height: dr * 2)
                context.stroke(Circle().path(in: drr),
                               with: .color(color.opacity(0.8)),
                               style: StrokeStyle(lineWidth: 2, dash: [4, 3]))
            }

            // Icon letter
            let letter = node.type == "human" ? "H" : "A"
            context.draw(
                Text(letter)
                    .font(.system(size: min(r * 0.7, 14), weight: .bold))
                    .foregroundColor(.white),
                at: sp
            )

            // Label (LOD)
            if showLabels {
                context.draw(
                    Text(node.label)
                        .font(.system(size: 11))
                        .foregroundColor(Color(red: 0.804, green: 0.839, blue: 0.957)),
                    at: CGPoint(x: sp.x, y: sp.y + r + 8)
                )
            }

            // Trust badge (LOD)
            if showTrustBadges {
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
        context.draw(
            Text(String(format: "%.1fx", currentScale))
                .font(.system(size: 10))
                .foregroundColor(Color.white.opacity(0.3)),
            at: CGPoint(x: 30, y: size.height - 16)
        )
    }

    // MARK: - Force Simulation (Barnes-Hut optimized)

    private func computePositions(in size: CGSize) {
        guard !nodes.isEmpty, size.width > 0, size.height > 0 else {
            positions = [:]
            return
        }

        let nodeCount = nodes.count
        var pos: [String: CGPoint] = Dictionary(minimumCapacity: nodeCount)
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        let spread = min(size.width, size.height) * 0.35

        // Initial radial placement
        for (i, node) in nodes.enumerated() {
            if node.isCenter {
                pos[node.id] = center
            } else {
                let angle = CGFloat(i) * 2.0 * .pi / CGFloat(max(1, nodeCount - 1))
                let r = node.connections.count > 2
                    ? spread * 0.5
                    : spread * CGFloat.random(in: 0.6...0.9)
                pos[node.id] = CGPoint(x: center.x + cos(angle) * r,
                                       y: center.y + sin(angle) * r)
            }
        }

        let nodeIds = nodes.map(\.id)

        // Adaptive iteration count: fewer iterations for very large graphs
        let iterations: Int
        if nodeCount > 500 {
            iterations = 40
        } else if nodeCount > 200 {
            iterations = 60
        } else {
            iterations = 80
        }

        // Use Barnes-Hut for graphs with 50+ nodes, brute force for small ones
        let useBarnesHut = nodeCount >= 50

        // Build index lookup once (not per iteration)
        let idToIndex: [String: Int] = Dictionary(
            uniqueKeysWithValues: nodeIds.enumerated().map { ($1, $0) }
        )

        for _ in 0..<iterations {
            // Pre-allocate force arrays (indexed, not dict — faster)
            var forcesX = [CGFloat](repeating: 0, count: nodeCount)
            var forcesY = [CGFloat](repeating: 0, count: nodeCount)

            // Collect current positions into arrays for fast indexed access
            var posX = [CGFloat](repeating: 0, count: nodeCount)
            var posY = [CGFloat](repeating: 0, count: nodeCount)
            for (i, nid) in nodeIds.enumerated() {
                if let p = pos[nid] {
                    posX[i] = p.x
                    posY[i] = p.y
                }
            }

            if useBarnesHut {
                // Build quadtree
                var minX: CGFloat = .greatestFiniteMagnitude
                var minY: CGFloat = .greatestFiniteMagnitude
                var maxX: CGFloat = -.greatestFiniteMagnitude
                var maxY: CGFloat = -.greatestFiniteMagnitude
                for i in 0..<nodeCount {
                    minX = min(minX, posX[i])
                    minY = min(minY, posY[i])
                    maxX = max(maxX, posX[i])
                    maxY = max(maxY, posY[i])
                }
                let treeSize = max(maxX - minX, maxY - minY) + 20
                let treeBounds = CGRect(x: minX - 10, y: minY - 10,
                                        width: treeSize, height: treeSize)
                let tree = QuadTreeNode(bounds: treeBounds)

                for i in 0..<nodeCount {
                    tree.insert(position: CGPoint(x: posX[i], y: posY[i]), index: i)
                }

                // Barnes-Hut repulsive forces
                for i in 0..<nodeCount {
                    var fx: CGFloat = 0
                    var fy: CGFloat = 0
                    tree.calculateForce(
                        on: CGPoint(x: posX[i], y: posY[i]),
                        theta: 0.8, fx: &fx, fy: &fy
                    )
                    forcesX[i] += fx
                    forcesY[i] += fy
                }
            } else {
                // Brute force O(n²) for small graphs — simpler and fast enough
                for i in 0..<nodeCount {
                    for j in (i + 1)..<nodeCount {
                        let dx = posX[j] - posX[i]
                        let dy = posY[j] - posY[i]
                        let distSq = max(dx * dx + dy * dy, 100)
                        let dist = sqrt(distSq)
                        let f: CGFloat = -50.0 / distSq
                        let fx = f * dx / dist
                        let fy = f * dy / dist
                        forcesX[i] += fx
                        forcesY[i] += fy
                        forcesX[j] -= fx
                        forcesY[j] -= fy
                    }
                }
            }

            // Attractive edge forces
            for edge in edges {
                guard let ai = idToIndex[edge.source],
                      let bi = idToIndex[edge.target] else { continue }
                let dx = posX[bi] - posX[ai]
                let dy = posY[bi] - posY[ai]
                let dist = max(sqrt(dx * dx + dy * dy), 1)
                let disp = dist - 120.0
                let fx = 0.05 * disp * dx / dist
                let fy = 0.05 * disp * dy / dist
                forcesX[ai] += fx
                forcesY[ai] += fy
                forcesX[bi] -= fx
                forcesY[bi] -= fy
            }

            // Center gravity
            for i in 0..<nodeCount {
                forcesX[i] += (center.x - posX[i]) * 0.002
                forcesY[i] += (center.y - posY[i]) * 0.002
            }

            // Apply forces with capping
            let cap: CGFloat = 15
            for (i, nid) in nodeIds.enumerated() {
                let mag = sqrt(forcesX[i] * forcesX[i] + forcesY[i] * forcesY[i])
                let sc = mag > cap ? cap / mag : 1.0
                let newX = posX[i] + forcesX[i] * sc
                let newY = posY[i] + forcesY[i] * sc
                pos[nid] = CGPoint(x: newX, y: newY)
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
        let ec = Self.edgeColorMap[type] ?? Self.defaultEdgeColor
        return Color(red: ec.r, green: ec.g, blue: ec.b)
    }

    private func edgeLineWidth(for edge: ForceEdge) -> CGFloat {
        switch edge.edgeType {
        case "attestation": CGFloat(1.0 + (edge.weight ?? 0.5) * 2.0)
        case "follow": 1.0
        default: 1.5
        }
    }
}
