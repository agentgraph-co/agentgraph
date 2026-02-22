// GraphViewModel — Fetch graph from API, compute layout (legacy radial fallback)
// Note: The primary graph view now uses ForceGraphViewModel with SpriteKit.
// This view model is retained for potential fallback usage.

import Foundation
import Observation

struct LayoutNode: Identifiable, Sendable {
    let id: String
    let label: String
    let type: String
    let trustScore: Double?
    let clusterId: Int?
    let x: Double
    let y: Double
    let isCenter: Bool
    let connections: [String]
}

@Observable @MainActor
final class GraphViewModel {
    var nodes: [LayoutNode] = []
    var edges: [(String, String)] = []
    var selectedNode: String?
    var nodeCount = 0
    var edgeCount = 0
    var isLoading = false
    var error: String?

    func loadGraph(centerId: UUID? = nil) async {
        isLoading = true
        error = nil

        do {
            let response: GraphResponse
            if let centerId {
                response = try await APIService.shared.getRichEgoGraph(entityId: centerId, depth: 2)
            } else {
                response = try await APIService.shared.getRichGraph(limit: 500)
            }

            nodeCount = response.nodeCount
            edgeCount = response.edgeCount

            // Build adjacency from edges
            var adjacency: [String: [String]] = [:]
            for edge in response.edges {
                adjacency[edge.source, default: []].append(edge.target)
                adjacency[edge.target, default: []].append(edge.source)
            }

            edges = response.edges.map { ($0.source, $0.target) }

            // Compute radial layout
            let apiNodes = response.nodes
            guard !apiNodes.isEmpty else {
                nodes = []
                isLoading = false
                return
            }

            // Pick center: most connected node, or centerId if provided
            let centerIdStr = centerId?.uuidString.lowercased()
            let centerNodeId = centerIdStr ?? apiNodes.max(by: {
                (adjacency[$0.id]?.count ?? 0) < (adjacency[$1.id]?.count ?? 0)
            })?.id ?? apiNodes[0].id

            var layoutNodes: [LayoutNode] = []
            let nonCenter = apiNodes.filter { $0.id != centerNodeId }
            let totalNonCenter = nonCenter.count
            var nonCenterIndex: [String: Int] = [:]
            for (i, node) in nonCenter.enumerated() {
                nonCenterIndex[node.id] = i
            }

            for apiNode in apiNodes {
                if apiNode.id == centerNodeId {
                    layoutNodes.append(LayoutNode(
                        id: apiNode.id,
                        label: apiNode.label,
                        type: apiNode.type,
                        trustScore: apiNode.trustScore,
                        clusterId: apiNode.clusterId,
                        x: 0, y: 0,
                        isCenter: true,
                        connections: adjacency[apiNode.id] ?? []
                    ))
                } else {
                    let idx = nonCenterIndex[apiNode.id] ?? 0
                    let angle = totalNonCenter > 0
                        ? (2.0 * .pi * Double(idx) / Double(totalNonCenter))
                        : 0
                    let connectionCount = adjacency[apiNode.id]?.count ?? 0
                    let radius = connectionCount > 2 ? 0.55 : 0.75
                    layoutNodes.append(LayoutNode(
                        id: apiNode.id,
                        label: apiNode.label,
                        type: apiNode.type,
                        trustScore: apiNode.trustScore,
                        clusterId: apiNode.clusterId,
                        x: cos(angle) * radius,
                        y: sin(angle) * radius,
                        isCenter: false,
                        connections: adjacency[apiNode.id] ?? []
                    ))
                }
            }

            nodes = layoutNodes
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func selectNode(_ id: String) {
        selectedNode = (selectedNode == id) ? nil : id
    }
}
