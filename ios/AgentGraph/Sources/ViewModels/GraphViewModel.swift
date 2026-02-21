// GraphViewModel — Fetch graph from API, compute layout

import Foundation
import Observation

struct LayoutNode: Identifiable, Sendable {
    let id: UUID
    let label: String
    let type: String
    let trustScore: Double?
    let x: Double
    let y: Double
    let isCenter: Bool
    let connections: [UUID]
}

@Observable @MainActor
final class GraphViewModel {
    var nodes: [LayoutNode] = []
    var edges: [(UUID, UUID)] = []
    var selectedNode: LayoutNode?
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
                response = try await APIService.shared.getEgoGraph(entityId: centerId, depth: 2)
            } else {
                response = try await APIService.shared.getGraph(limit: 80)
            }

            nodeCount = response.nodeCount
            edgeCount = response.edgeCount

            // Build adjacency from edges
            var adjacency: [UUID: [UUID]] = [:]
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
            let centerNodeId = centerId ?? apiNodes.max(by: {
                (adjacency[$0.id]?.count ?? 0) < (adjacency[$1.id]?.count ?? 0)
            })?.id ?? apiNodes[0].id

            var layoutNodes: [LayoutNode] = []
            let nonCenter = apiNodes.filter { $0.id != centerNodeId }
            let totalNonCenter = nonCenter.count

            for (i, apiNode) in apiNodes.enumerated() {
                if apiNode.id == centerNodeId {
                    layoutNodes.append(LayoutNode(
                        id: apiNode.id,
                        label: apiNode.label,
                        type: apiNode.type,
                        trustScore: apiNode.trustScore,
                        x: 0, y: 0,
                        isCenter: true,
                        connections: adjacency[apiNode.id] ?? []
                    ))
                } else {
                    let idx = nonCenter.firstIndex(where: { $0.id == apiNode.id }) ?? i
                    let angle = totalNonCenter > 0
                        ? (2.0 * .pi * Double(idx) / Double(totalNonCenter))
                        : 0
                    let radius = 0.7
                    layoutNodes.append(LayoutNode(
                        id: apiNode.id,
                        label: apiNode.label,
                        type: apiNode.type,
                        trustScore: apiNode.trustScore,
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
}
