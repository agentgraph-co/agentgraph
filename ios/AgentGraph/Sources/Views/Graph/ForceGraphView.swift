// ForceGraphView — SpriteKit force-directed graph wrapped in SwiftUI

import SpriteKit
import SwiftUI

// MARK: - SwiftUI Wrapper

struct ForceGraphView: View {
    let nodes: [ForceNode]
    let edges: [ForceEdge]
    var onNodeTap: ((String) -> Void)?
    var onNodeLongPress: ((String) -> Void)?
    var selectedNodeId: String?

    @State private var scene: ForceGraphScene?

    var body: some View {
        GeometryReader { geo in
            if let scene {
                SpriteView(scene: scene, options: [.allowsTransparency])
                    .ignoresSafeArea()
                    .onChange(of: nodes.count) {
                        scene.updateGraph(nodes: nodes, edges: edges, selectedNodeId: selectedNodeId)
                    }
                    .onChange(of: selectedNodeId) {
                        scene.updateSelection(selectedNodeId)
                    }
            } else {
                Color.clear
                    .onAppear {
                        let newScene = ForceGraphScene(size: geo.size)
                        newScene.scaleMode = .resizeFill
                        newScene.backgroundColor = .clear
                        newScene.onNodeTap = onNodeTap
                        newScene.onNodeLongPress = onNodeLongPress
                        newScene.updateGraph(nodes: nodes, edges: edges, selectedNodeId: selectedNodeId)
                        scene = newScene
                    }
            }
        }
    }
}

// MARK: - SpriteKit Scene

final class ForceGraphScene: SKScene {
    var onNodeTap: ((String) -> Void)?
    var onNodeLongPress: ((String) -> Void)?

    private var nodeSprites: [String: SKNode] = [:]
    private var edgeSprites: [String: SKShapeNode] = [:]
    private var labelNodes: [String: SKLabelNode] = [:]
    private var iconNodes: [String: SKLabelNode] = [:]
    private var graphNodes: [String: ForceNode] = [:]
    private var graphEdges: [ForceEdge] = []
    private var currentSelectedId: String?

    // Camera for zoom/pan
    private var cameraNode = SKCameraNode()
    private var currentScale: CGFloat = 1.0
    private var lastPinchScale: CGFloat = 1.0

    // Long press detection
    private var touchStartTime: TimeInterval = 0
    private var touchStartNode: String?
    private let longPressThreshold: TimeInterval = 0.5

    // LOD thresholds
    private let labelZoomThreshold: CGFloat = 0.5   // Show labels when zoomed in past 2x (camera scale < 0.5)
    private let hideSmallNodeThreshold: CGFloat = 2.0  // Hide small nodes when zoomed out past 2x (camera scale > 2.0)

    // Physics constants
    private let centerAttraction: Float = 0.2
    private let nodeRepulsion: Float = -50.0
    private let springLength: Float = 120.0
    private let damping: Float = 0.9

    override func didMove(to view: SKView) {
        backgroundColor = .clear
        physicsWorld.gravity = CGVector(dx: 0, dy: 0)

        cameraNode.position = CGPoint(x: size.width / 2, y: size.height / 2)
        addChild(cameraNode)
        camera = cameraNode

        // Add pinch gesture for zoom
        let pinch = UIPinchGestureRecognizer(target: self, action: #selector(handlePinch(_:)))
        view.addGestureRecognizer(pinch)

        // Add pan gesture for drag
        let pan = UIPanGestureRecognizer(target: self, action: #selector(handlePan(_:)))
        pan.minimumNumberOfTouches = 2
        view.addGestureRecognizer(pan)
    }

    // MARK: - Gesture Handlers

    @objc private func handlePinch(_ gesture: UIPinchGestureRecognizer) {
        switch gesture.state {
        case .began:
            lastPinchScale = currentScale
        case .changed:
            let newScale = lastPinchScale / gesture.scale
            currentScale = max(0.2, min(5.0, newScale))
            cameraNode.setScale(currentScale)
            updateLOD()
        case .ended:
            lastPinchScale = currentScale
        default:
            break
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

    // MARK: - Touch Handling (Tap and Long Press on Nodes)

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let touch = touches.first else { return }
        let location = touch.location(in: self)
        touchStartTime = touch.timestamp

        // Find touched node
        touchStartNode = nil
        let touchedNodes = nodes(at: location)
        for touched in touchedNodes {
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

    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let touch = touches.first, let nodeId = touchStartNode else {
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
        // Clear existing
        removeAllChildren()
        nodeSprites.removeAll()
        edgeSprites.removeAll()
        labelNodes.removeAll()
        iconNodes.removeAll()
        graphNodes.removeAll()
        graphEdges = edges
        currentSelectedId = selectedNodeId

        // Re-add camera
        addChild(cameraNode)
        camera = cameraNode
        cameraNode.position = CGPoint(x: size.width / 2, y: size.height / 2)

        guard !nodes.isEmpty else { return }

        // Store node data
        for node in nodes {
            graphNodes[node.id] = node
        }

        // Create edge shapes (drawn below nodes)
        for edge in edges {
            let edgeLine = SKShapeNode()
            edgeLine.strokeColor = edgeColor(for: edge.edgeType)
            edgeLine.lineWidth = edgeLineWidth(for: edge)
            edgeLine.alpha = 0.4
            edgeLine.zPosition = 0
            addChild(edgeLine)
            edgeSprites[edge.id] = edgeLine
        }

        // Create node sprites with physics
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        let spreadRadius = min(size.width, size.height) * 0.35
        let nodeCount = nodes.count

        for (index, node) in nodes.enumerated() {
            // Initial position: spiral layout for better starting positions
            let angle: CGFloat
            let radius: CGFloat
            if node.isCenter {
                angle = 0
                radius = 0
            } else {
                angle = CGFloat(index) * 2.0 * .pi / CGFloat(max(1, nodeCount - 1))
                let connectionCount = node.connections.count
                radius = connectionCount > 2
                    ? spreadRadius * 0.5
                    : spreadRadius * CGFloat.random(in: 0.6...0.9)
            }

            let position = CGPoint(
                x: center.x + cos(angle) * radius,
                y: center.y + sin(angle) * radius
            )

            let container = createNodeSprite(node: node, at: position, isSelected: node.id == selectedNodeId)
            nodeSprites[node.id] = container
        }

        // Apply initial force simulation steps
        simulateForces(steps: 80)

        // Update edge paths after simulation
        updateEdgePaths()
        updateLOD()
    }

    func updateSelection(_ selectedId: String?) {
        // Remove old selection highlight
        if let oldId = currentSelectedId, let oldSprite = nodeSprites[oldId] {
            oldSprite.childNode(withName: "selectionRing")?.removeFromParent()
        }

        currentSelectedId = selectedId

        // Add new selection highlight
        if let newId = selectedId, let newSprite = nodeSprites[newId],
           let node = graphNodes[newId] {
            let ring = SKShapeNode(circleOfRadius: node.radius + 4)
            ring.name = "selectionRing"
            ring.strokeColor = .white
            ring.lineWidth = 2
            ring.fillColor = .clear
            ring.glowWidth = 3
            ring.zPosition = 10
            newSprite.addChild(ring)
        }
    }

    // MARK: - Node Creation

    private func createNodeSprite(node: ForceNode, at position: CGPoint, isSelected: Bool) -> SKNode {
        let container = SKNode()
        container.position = position
        container.zPosition = 5
        container.userData = NSMutableDictionary()
        container.userData?["nodeId"] = node.id

        // Physics body for force simulation
        let body = SKPhysicsBody(circleOfRadius: node.radius + 2)
        body.isDynamic = true
        body.mass = CGFloat(1.0 + node.trustScore * 2.0)
        body.linearDamping = CGFloat(damping)
        body.allowsRotation = false
        body.friction = 0.3
        body.restitution = 0.2
        // Prevent actual collision response -- we just want forces
        body.categoryBitMask = 0x1
        body.collisionBitMask = 0x1
        body.contactTestBitMask = 0
        container.physicsBody = body

        // Glow effect
        let glowRadius = node.radius * 1.8
        let glow = SKShapeNode(circleOfRadius: glowRadius)
        let clusterColor = ForceGraphViewModel.colorForCluster(node.clusterId)
        glow.fillColor = SKColor(
            red: clusterColor.red,
            green: clusterColor.green,
            blue: clusterColor.blue,
            alpha: 0.15
        )
        glow.strokeColor = .clear
        glow.zPosition = -1
        container.addChild(glow)

        // Main circle
        let circle = SKShapeNode(circleOfRadius: node.radius)
        circle.fillColor = SKColor(
            red: clusterColor.red,
            green: clusterColor.green,
            blue: clusterColor.blue,
            alpha: 1.0
        )
        circle.strokeColor = SKColor(
            red: clusterColor.red,
            green: clusterColor.green,
            blue: clusterColor.blue,
            alpha: 0.7
        )
        circle.lineWidth = node.isCenter ? 3 : 1.5
        circle.name = "circle"
        circle.userData = NSMutableDictionary()
        circle.userData?["nodeId"] = node.id
        container.addChild(circle)

        // Entity type icon
        let icon = SKLabelNode(text: node.type == "human" ? "\u{1F464}" : "\u{1F4BB}")
        icon.fontSize = node.radius * 0.9
        icon.verticalAlignmentMode = .center
        icon.horizontalAlignmentMode = .center
        icon.zPosition = 6
        container.addChild(icon)
        iconNodes[node.id] = icon

        // Label
        let label = SKLabelNode(text: node.label)
        label.fontSize = 11
        label.fontColor = SKColor(red: 0.804, green: 0.839, blue: 0.957, alpha: 1.0) // agText
        label.verticalAlignmentMode = .top
        label.horizontalAlignmentMode = .center
        label.position = CGPoint(x: 0, y: -(node.radius + 6))
        label.zPosition = 7
        container.addChild(label)
        labelNodes[node.id] = label

        // Selection ring
        if isSelected {
            let ring = SKShapeNode(circleOfRadius: node.radius + 4)
            ring.name = "selectionRing"
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

        // Build edge lookup for spring forces
        var edgeSet = Set<String>()
        var adjacency: [String: [String]] = [:]
        for edge in graphEdges {
            let key = [edge.source, edge.target].sorted().joined(separator: "-")
            edgeSet.insert(key)
            adjacency[edge.source, default: []].append(edge.target)
            adjacency[edge.target, default: []].append(edge.source)
        }

        for _ in 0..<steps {
            var forces: [String: CGVector] = [:]
            for nid in nodeIds {
                forces[nid] = .zero
            }

            // Repulsion between all pairs (Barnes-Hut would be better for 500+, but OK for now)
            for i in 0..<count {
                for j in (i + 1)..<count {
                    let idA = nodeIds[i]
                    let idB = nodeIds[j]
                    guard let spriteA = nodeSprites[idA],
                          let spriteB = nodeSprites[idB] else { continue }

                    let dx = spriteB.position.x - spriteA.position.x
                    let dy = spriteB.position.y - spriteA.position.y
                    let distSq = max(dx * dx + dy * dy, 100)
                    let dist = sqrt(distSq)

                    let force = CGFloat(nodeRepulsion) / distSq
                    let fx = force * dx / dist
                    let fy = force * dy / dist

                    forces[idA] = CGVector(dx: (forces[idA]?.dx ?? 0) + fx,
                                           dy: (forces[idA]?.dy ?? 0) + fy)
                    forces[idB] = CGVector(dx: (forces[idB]?.dx ?? 0) - fx,
                                           dy: (forces[idB]?.dy ?? 0) - fy)
                }
            }

            // Spring forces along edges
            for edge in graphEdges {
                guard let spriteA = nodeSprites[edge.source],
                      let spriteB = nodeSprites[edge.target] else { continue }

                let dx = spriteB.position.x - spriteA.position.x
                let dy = spriteB.position.y - spriteA.position.y
                let dist = max(sqrt(dx * dx + dy * dy), 1)
                let displacement = dist - CGFloat(springLength)

                let fx = 0.05 * displacement * dx / dist
                let fy = 0.05 * displacement * dy / dist

                forces[edge.source] = CGVector(dx: (forces[edge.source]?.dx ?? 0) + fx,
                                               dy: (forces[edge.source]?.dy ?? 0) + fy)
                forces[edge.target] = CGVector(dx: (forces[edge.target]?.dx ?? 0) - fx,
                                               dy: (forces[edge.target]?.dy ?? 0) - fy)
            }

            // Center gravity
            for nid in nodeIds {
                guard let sprite = nodeSprites[nid] else { continue }
                let dx = center.x - sprite.position.x
                let dy = center.y - sprite.position.y

                forces[nid] = CGVector(
                    dx: (forces[nid]?.dx ?? 0) + dx * CGFloat(centerAttraction) * 0.01,
                    dy: (forces[nid]?.dy ?? 0) + dy * CGFloat(centerAttraction) * 0.01
                )
            }

            // Apply forces
            for nid in nodeIds {
                guard let sprite = nodeSprites[nid],
                      let force = forces[nid] else { continue }

                // Clamp force magnitude
                let mag = sqrt(force.dx * force.dx + force.dy * force.dy)
                let maxForce: CGFloat = 15
                let scale = mag > maxForce ? maxForce / mag : 1.0

                sprite.position = CGPoint(
                    x: sprite.position.x + force.dx * scale,
                    y: sprite.position.y + force.dy * scale
                )
            }
        }

        // Stop physics bodies from moving after simulation
        for (_, sprite) in nodeSprites {
            sprite.physicsBody?.velocity = .zero
            sprite.physicsBody?.isDynamic = false
        }
    }

    // MARK: - Edge Drawing

    private func updateEdgePaths() {
        for edge in graphEdges {
            guard let edgeLine = edgeSprites[edge.id],
                  let sourceSprite = nodeSprites[edge.source],
                  let targetSprite = nodeSprites[edge.target] else { continue }

            let path = CGMutablePath()
            path.move(to: sourceSprite.position)
            path.addLine(to: targetSprite.position)
            edgeLine.path = path
        }
    }

    // MARK: - Level of Detail

    private func updateLOD() {
        let showLabels = currentScale < labelZoomThreshold
        let hideSmall = currentScale > hideSmallNodeThreshold

        for (nodeId, label) in labelNodes {
            label.isHidden = !showLabels
        }

        if hideSmall {
            for (nodeId, sprite) in nodeSprites {
                guard let node = graphNodes[nodeId] else { continue }
                // Hide nodes with small radius (low trust)
                sprite.isHidden = node.radius < 14 && !node.isCenter
            }
        } else {
            for (_, sprite) in nodeSprites {
                sprite.isHidden = false
            }
        }
    }

    // MARK: - Edge Styling

    private func edgeColor(for type: String) -> SKColor {
        switch type {
        case "follow":
            return SKColor(red: 0.118, green: 0.200, blue: 0.200, alpha: 1.0) // agBorder
        case "attestation":
            return SKColor(red: 0.651, green: 0.890, blue: 0.631, alpha: 1.0) // agSuccess
        case "operator_agent":
            return SKColor(red: 0.537, green: 0.706, blue: 0.980, alpha: 1.0) // Blue
        case "collaboration":
            return SKColor(red: 0.796, green: 0.651, blue: 0.969, alpha: 1.0) // Mauve
        case "service":
            return SKColor(red: 0.980, green: 0.702, blue: 0.529, alpha: 1.0) // Peach
        default:
            return SKColor(red: 0.424, green: 0.439, blue: 0.525, alpha: 1.0) // agMuted
        }
    }

    private func edgeLineWidth(for edge: ForceEdge) -> CGFloat {
        switch edge.edgeType {
        case "attestation":
            return CGFloat(1.0 + (edge.weight ?? 0.5) * 2.0)
        case "follow":
            return 1.0
        default:
            return 1.5
        }
    }

    override func update(_ currentTime: TimeInterval) {
        // No continuous updates needed since we pre-compute layout
    }
}
