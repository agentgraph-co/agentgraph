// ForceGraphView — SpriteKit force-directed graph wrapped in SwiftUI
// Uses SpriteKit camera for zoom/pan (not UIGestureRecognizers which conflict with SwiftUI)

import SpriteKit
import SwiftUI

// MARK: - UIKit Hosting (bypasses SwiftUI gesture conflicts)

struct ForceGraphView: UIViewRepresentable {
    let nodes: [ForceNode]
    let edges: [ForceEdge]
    var onNodeTap: ((String) -> Void)?
    var onNodeLongPress: ((String) -> Void)?
    var selectedNodeId: String?

    func makeUIView(context: Context) -> SKView {
        let skView = SKView()
        skView.allowsTransparency = true
        skView.backgroundColor = .clear

        let scene = ForceGraphScene(size: UIScreen.main.bounds.size)
        scene.scaleMode = .resizeFill
        scene.backgroundColor = .clear
        scene.onNodeTap = onNodeTap
        scene.onNodeLongPress = onNodeLongPress
        scene.updateGraph(nodes: nodes, edges: edges, selectedNodeId: selectedNodeId)
        context.coordinator.scene = scene
        skView.presentScene(scene)

        return skView
    }

    func updateUIView(_ skView: SKView, context: Context) {
        guard let scene = context.coordinator.scene else { return }

        // Only rebuild if node set actually changed
        let currentIds = Set(scene.currentNodeIds)
        let newIds = Set(nodes.map(\.id))
        if currentIds != newIds {
            scene.onNodeTap = onNodeTap
            scene.onNodeLongPress = onNodeLongPress
            scene.updateGraph(nodes: nodes, edges: edges, selectedNodeId: selectedNodeId)
        } else {
            scene.updateSelection(selectedNodeId)
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    class Coordinator {
        var scene: ForceGraphScene?
    }
}

// MARK: - SpriteKit Scene

final class ForceGraphScene: SKScene {
    var onNodeTap: ((String) -> Void)?
    var onNodeLongPress: ((String) -> Void)?

    /// Expose current node IDs so the wrapper can detect changes
    var currentNodeIds: [String] { Array(graphNodes.keys) }

    private var nodeSprites: [String: SKNode] = [:]
    private var edgeSprites: [String: SKShapeNode] = [:]
    private var labelNodes: [String: SKLabelNode] = [:]
    private var graphNodes: [String: ForceNode] = [:]
    private var graphEdges: [ForceEdge] = []
    private var currentSelectedId: String?

    // Camera for zoom/pan
    private let cameraNode = SKCameraNode()
    private var currentScale: CGFloat = 1.0

    // Touch tracking
    private var touchStartTime: TimeInterval = 0
    private var touchStartNode: String?
    private var touchStartPosition: CGPoint = .zero
    private var isPanning = false
    private let longPressThreshold: TimeInterval = 0.5
    private let panThreshold: CGFloat = 10

    // LOD
    private let labelZoomThreshold: CGFloat = 0.6
    private let hideSmallNodeThreshold: CGFloat = 2.0

    // Force sim constants
    private let centerAttraction: Float = 0.2
    private let nodeRepulsion: Float = -50.0
    private let springLength: Float = 120.0
    private let damping: Float = 0.9

    override func didMove(to view: SKView) {
        backgroundColor = .clear
        physicsWorld.gravity = .zero

        if cameraNode.parent == nil {
            addChild(cameraNode)
        }
        camera = cameraNode
        cameraNode.position = CGPoint(x: size.width / 2, y: size.height / 2)

        // Use native gesture recognizers on the SKView
        let pinch = UIPinchGestureRecognizer(target: self, action: #selector(handlePinch(_:)))
        view.addGestureRecognizer(pinch)

        let pan = UIPanGestureRecognizer(target: self, action: #selector(handlePan(_:)))
        pan.minimumNumberOfTouches = 2
        view.addGestureRecognizer(pan)
    }

    // MARK: - Gesture Handlers

    @objc private func handlePinch(_ gesture: UIPinchGestureRecognizer) {
        if gesture.state == .changed {
            let newScale = currentScale / gesture.scale
            currentScale = max(0.3, min(4.0, newScale))
            cameraNode.setScale(currentScale)
            gesture.scale = 1.0
            updateLOD()
        }
    }

    @objc private func handlePan(_ gesture: UIPanGestureRecognizer) {
        guard let view = self.view else { return }
        let translation = gesture.translation(in: view)
        cameraNode.position = CGPoint(
            x: cameraNode.position.x - translation.x * currentScale,
            y: cameraNode.position.y + translation.y * currentScale
        )
        gesture.setTranslation(.zero, in: view)
    }

    // MARK: - Single-finger touch: tap / long-press on nodes

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let touch = touches.first else { return }
        let location = touch.location(in: self)
        touchStartTime = touch.timestamp
        touchStartPosition = location
        isPanning = false

        touchStartNode = nil
        for touched in nodes(at: location) {
            if let nodeId = touched.userData?["nodeId"] as? String {
                touchStartNode = nodeId
                break
            }
            if let parentId = touched.parent?.userData?["nodeId"] as? String {
                touchStartNode = parentId
                break
            }
        }
    }

    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let touch = touches.first else { return }
        let location = touch.location(in: self)
        let dx = location.x - touchStartPosition.x
        let dy = location.y - touchStartPosition.y
        if sqrt(dx * dx + dy * dy) > panThreshold {
            isPanning = true
        }
    }

    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let touch = touches.first else {
            touchStartNode = nil
            return
        }

        // If finger moved significantly, it was a drag not a tap
        guard !isPanning, let nodeId = touchStartNode else {
            touchStartNode = nil
            return
        }

        let duration = touch.timestamp - touchStartTime
        if duration >= longPressThreshold {
            onNodeLongPress?(nodeId)
        } else {
            onNodeTap?(nodeId)
        }
        touchStartNode = nil
    }

    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
        touchStartNode = nil
    }

    // MARK: - Graph Management

    func updateGraph(nodes: [ForceNode], edges: [ForceEdge], selectedNodeId: String?) {
        removeAllChildren()
        nodeSprites.removeAll()
        edgeSprites.removeAll()
        labelNodes.removeAll()
        graphNodes.removeAll()
        graphEdges = edges
        currentSelectedId = selectedNodeId

        addChild(cameraNode)
        camera = cameraNode
        currentScale = 1.0
        cameraNode.setScale(1.0)
        cameraNode.position = CGPoint(x: size.width / 2, y: size.height / 2)

        guard !nodes.isEmpty, size.width > 0, size.height > 0 else { return }

        for node in nodes {
            graphNodes[node.id] = node
        }

        // Edges first (below nodes)
        for edge in edges {
            let line = SKShapeNode()
            line.strokeColor = edgeColor(for: edge.edgeType)
            line.lineWidth = edgeLineWidth(for: edge)
            line.alpha = 0.4
            line.zPosition = 0
            addChild(line)
            edgeSprites[edge.id] = line
        }

        // Nodes
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        let spread = min(size.width, size.height) * 0.35
        let count = nodes.count

        for (i, node) in nodes.enumerated() {
            let angle: CGFloat
            let r: CGFloat
            if node.isCenter {
                angle = 0; r = 0
            } else {
                angle = CGFloat(i) * 2.0 * .pi / CGFloat(max(1, count - 1))
                r = node.connections.count > 2
                    ? spread * 0.5
                    : spread * CGFloat.random(in: 0.6...0.9)
            }

            let pos = CGPoint(x: center.x + cos(angle) * r, y: center.y + sin(angle) * r)
            let sprite = createNode(node, at: pos, selected: node.id == selectedNodeId)
            nodeSprites[node.id] = sprite
        }

        simulateForces(steps: 80)
        updateEdgePaths()
        updateLOD()
    }

    func updateSelection(_ selectedId: String?) {
        if let oldId = currentSelectedId, let sprite = nodeSprites[oldId] {
            sprite.childNode(withName: "ring")?.removeFromParent()
        }
        currentSelectedId = selectedId
        if let newId = selectedId, let sprite = nodeSprites[newId],
           let node = graphNodes[newId] {
            let ring = SKShapeNode(circleOfRadius: node.radius + 4)
            ring.name = "ring"
            ring.strokeColor = .white
            ring.lineWidth = 2
            ring.fillColor = .clear
            ring.glowWidth = 3
            ring.zPosition = 10
            sprite.addChild(ring)
        }
    }

    // MARK: - Node Creation

    private func createNode(_ node: ForceNode, at position: CGPoint, selected: Bool) -> SKNode {
        let container = SKNode()
        container.position = position
        container.zPosition = 5
        container.userData = ["nodeId": node.id] as NSMutableDictionary

        // Physics body (used only during force sim, then frozen)
        let body = SKPhysicsBody(circleOfRadius: node.radius + 2)
        body.isDynamic = true
        body.mass = CGFloat(1.0 + node.trustScore * 2.0)
        body.linearDamping = CGFloat(damping)
        body.allowsRotation = false
        body.categoryBitMask = 0x1
        body.collisionBitMask = 0x1
        body.contactTestBitMask = 0
        container.physicsBody = body

        let cc = ForceGraphViewModel.colorForCluster(node.clusterId)

        // Glow
        let glow = SKShapeNode(circleOfRadius: node.radius * 1.8)
        glow.fillColor = SKColor(red: cc.red, green: cc.green, blue: cc.blue, alpha: 0.15)
        glow.strokeColor = .clear
        glow.zPosition = -1
        container.addChild(glow)

        // Circle
        let circle = SKShapeNode(circleOfRadius: node.radius)
        circle.fillColor = SKColor(red: cc.red, green: cc.green, blue: cc.blue, alpha: 1)
        circle.strokeColor = SKColor(red: cc.red, green: cc.green, blue: cc.blue, alpha: 0.7)
        circle.lineWidth = node.isCenter ? 3 : 1.5
        circle.userData = ["nodeId": node.id] as NSMutableDictionary
        container.addChild(circle)

        // Icon letter
        let icon = SKLabelNode(text: node.type == "human" ? "H" : "A")
        icon.fontSize = node.radius * 0.7
        icon.fontName = "Helvetica-Bold"
        icon.fontColor = .white
        icon.verticalAlignmentMode = .center
        icon.horizontalAlignmentMode = .center
        icon.zPosition = 6
        container.addChild(icon)

        // Label
        let label = SKLabelNode(text: node.label)
        label.fontSize = 11
        label.fontColor = SKColor(red: 0.804, green: 0.839, blue: 0.957, alpha: 1)
        label.verticalAlignmentMode = .top
        label.horizontalAlignmentMode = .center
        label.position = CGPoint(x: 0, y: -(node.radius + 6))
        label.zPosition = 7
        container.addChild(label)
        labelNodes[node.id] = label

        if selected {
            let ring = SKShapeNode(circleOfRadius: node.radius + 4)
            ring.name = "ring"
            ring.strokeColor = .white
            ring.lineWidth = 2
            ring.fillColor = .clear
            ring.glowWidth = 3
            ring.zPosition = 10
            container.addChild(ring)
        }

        addChild(container)
        return container
    }

    // MARK: - Force Simulation

    private func simulateForces(steps: Int) {
        let nodeIds = Array(graphNodes.keys)
        let count = nodeIds.count
        guard count > 1 else { return }

        let center = CGPoint(x: size.width / 2, y: size.height / 2)

        for _ in 0..<steps {
            var forces: [String: CGVector] = [:]
            for nid in nodeIds { forces[nid] = .zero }

            // Repulsion
            for i in 0..<count {
                for j in (i + 1)..<count {
                    let a = nodeIds[i], b = nodeIds[j]
                    guard let sa = nodeSprites[a], let sb = nodeSprites[b] else { continue }
                    let dx = sb.position.x - sa.position.x
                    let dy = sb.position.y - sa.position.y
                    let distSq = max(dx * dx + dy * dy, 100)
                    let dist = sqrt(distSq)
                    let f = CGFloat(nodeRepulsion) / distSq
                    let fx = f * dx / dist, fy = f * dy / dist
                    forces[a]!.dx += fx; forces[a]!.dy += fy
                    forces[b]!.dx -= fx; forces[b]!.dy -= fy
                }
            }

            // Springs
            for edge in graphEdges {
                guard let sa = nodeSprites[edge.source], let sb = nodeSprites[edge.target] else { continue }
                let dx = sb.position.x - sa.position.x
                let dy = sb.position.y - sa.position.y
                let dist = max(sqrt(dx * dx + dy * dy), 1)
                let disp = dist - CGFloat(springLength)
                let fx = 0.05 * disp * dx / dist, fy = 0.05 * disp * dy / dist
                forces[edge.source]!.dx += fx; forces[edge.source]!.dy += fy
                forces[edge.target]!.dx -= fx; forces[edge.target]!.dy -= fy
            }

            // Gravity
            for nid in nodeIds {
                guard let s = nodeSprites[nid] else { continue }
                let dx = center.x - s.position.x, dy = center.y - s.position.y
                forces[nid]!.dx += dx * CGFloat(centerAttraction) * 0.01
                forces[nid]!.dy += dy * CGFloat(centerAttraction) * 0.01
            }

            // Apply
            for nid in nodeIds {
                guard let s = nodeSprites[nid], let f = forces[nid] else { continue }
                let mag = sqrt(f.dx * f.dx + f.dy * f.dy)
                let cap: CGFloat = 15
                let sc = mag > cap ? cap / mag : 1.0
                s.position = CGPoint(x: s.position.x + f.dx * sc, y: s.position.y + f.dy * sc)
            }
        }

        // Freeze
        for (_, s) in nodeSprites {
            s.physicsBody?.velocity = .zero
            s.physicsBody?.isDynamic = false
        }
    }

    // MARK: - Edges

    private func updateEdgePaths() {
        for edge in graphEdges {
            guard let line = edgeSprites[edge.id],
                  let src = nodeSprites[edge.source],
                  let dst = nodeSprites[edge.target] else { continue }
            let path = CGMutablePath()
            path.move(to: src.position)
            path.addLine(to: dst.position)
            line.path = path
        }
    }

    // MARK: - LOD

    private func updateLOD() {
        let showLabels = currentScale < labelZoomThreshold
        let hideSmall = currentScale > hideSmallNodeThreshold

        for (_, label) in labelNodes { label.isHidden = !showLabels }

        for (nid, sprite) in nodeSprites {
            if hideSmall, let node = graphNodes[nid] {
                sprite.isHidden = node.radius < 14 && !node.isCenter
            } else {
                sprite.isHidden = false
            }
        }
    }

    // MARK: - Styling

    private func edgeColor(for type: String) -> SKColor {
        switch type {
        case "follow": SKColor(red: 0.118, green: 0.200, blue: 0.200, alpha: 1)
        case "attestation": SKColor(red: 0.651, green: 0.890, blue: 0.631, alpha: 1)
        case "operator_agent": SKColor(red: 0.537, green: 0.706, blue: 0.980, alpha: 1)
        case "collaboration": SKColor(red: 0.796, green: 0.651, blue: 0.969, alpha: 1)
        case "service": SKColor(red: 0.980, green: 0.702, blue: 0.529, alpha: 1)
        default: SKColor(red: 0.424, green: 0.439, blue: 0.525, alpha: 1)
        }
    }

    private func edgeLineWidth(for edge: ForceEdge) -> CGFloat {
        switch edge.edgeType {
        case "attestation": CGFloat(1.0 + (edge.weight ?? 0.5) * 2.0)
        case "follow": 1.0
        default: 1.5
        }
    }

    override func update(_ currentTime: TimeInterval) {}
}
