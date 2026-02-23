// ForceGraphViewModel — State management for SpriteKit force-directed graph

import Foundation
import Observation

/// A node in the force-directed graph layout with physics properties.
struct ForceNode: Identifiable, Sendable {
    let id: String
    let label: String
    let type: String        // "human" or "agent"
    let trustScore: Double
    let clusterId: Int?
    let isCenter: Bool
    var connections: [String]

    /// Radius based on trust score: higher trust = larger node
    var radius: CGFloat {
        CGFloat(8 + trustScore * 24)
    }
}

/// An edge in the force-directed graph.
struct ForceEdge: Identifiable, Sendable {
    let id: String
    let source: String
    let target: String
    let edgeType: String
    let weight: Double?

    init(source: String, target: String, edgeType: String, weight: Double? = nil) {
        self.id = "\(source)-\(target)-\(edgeType)"
        self.source = source
        self.target = target
        self.edgeType = edgeType
        self.weight = weight
    }
}

@Observable @MainActor
final class ForceGraphViewModel {
    var nodes: [ForceNode] = []
    var edges: [ForceEdge] = []
    var clusters: [ClusterInfo] = []
    var selectedNodeId: String?
    var nodeCount = 0
    var edgeCount = 0
    var isLoading = false
    var error: String?
    var showClusters = true
    var trustFlowResponse: TrustFlowResponse?
    var showTrustFlow = false
    var layoutId = UUID()

    // Catppuccin Mocha cluster colors (hex values from task spec)
    static let clusterColors: [(red: Double, green: Double, blue: Double)] = [
        (0.953, 0.545, 0.659),  // Red #f38ba8
        (0.980, 0.702, 0.529),  // Peach #fab387
        (0.976, 0.886, 0.686),  // Yellow #f9e2af
        (0.651, 0.890, 0.631),  // Green #a6e3a1
        (0.580, 0.886, 0.835),  // Teal #94e2d5
        (0.537, 0.706, 0.980),  // Blue #89b4fa
        (0.706, 0.745, 0.996),  // Lavender #b4befe
        (0.796, 0.651, 0.969),  // Mauve #cba6f7
        (0.949, 0.804, 0.804),  // Flamingo #f2cdcd
        (0.961, 0.878, 0.863),  // Rosewater #f5e0dc
    ]

    /// Returns the color components for a given cluster ID.
    static func colorForCluster(_ clusterId: Int?) -> (red: Double, green: Double, blue: Double) {
        guard let cid = clusterId else {
            return (0.424, 0.439, 0.525)  // agMuted
        }
        return clusterColors[cid % clusterColors.count]
    }

    func loadRichGraph(centerId: UUID? = nil) async {
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

            // Build adjacency
            var adjacency: [String: [String]] = [:]
            for edge in response.edges {
                adjacency[edge.source, default: []].append(edge.target)
                adjacency[edge.target, default: []].append(edge.source)
            }

            // Determine center node
            let centerIdStr = centerId?.uuidString.lowercased()
            let centerNodeId = centerIdStr ?? response.nodes.max(by: {
                (adjacency[$0.id]?.count ?? 0) < (adjacency[$1.id]?.count ?? 0)
            })?.id ?? response.nodes.first?.id

            // Map API nodes to ForceNodes
            nodes = response.nodes.map { apiNode in
                ForceNode(
                    id: apiNode.id,
                    label: apiNode.label,
                    type: apiNode.type,
                    trustScore: apiNode.trustScore ?? 0.0,
                    clusterId: apiNode.clusterId,
                    isCenter: apiNode.id == centerNodeId,
                    connections: adjacency[apiNode.id] ?? []
                )
            }

            // Map API edges to ForceEdges
            edges = response.edges.map { apiEdge in
                ForceEdge(
                    source: apiEdge.source,
                    target: apiEdge.target,
                    edgeType: apiEdge.type,
                    weight: apiEdge.weight
                )
            }

            // Load clusters
            await loadClusters()

            // Bump layoutId so ForceGraphView re-computes positions
            layoutId = UUID()

        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func loadClusters() async {
        do {
            let response = try await APIService.shared.getClusters()
            clusters = response.clusters
        } catch {
            // Non-critical: clusters are optional
            clusters = []
        }
    }

    func loadTrustFlow(entityId: String) async {
        guard let uuid = UUID(uuidString: entityId) else { return }
        do {
            trustFlowResponse = try await APIService.shared.getTrustFlow(entityId: uuid, depth: 2)
            showTrustFlow = true
        } catch {
            trustFlowResponse = nil
        }
    }

    func selectNode(_ id: String?) {
        selectedNodeId = (selectedNodeId == id) ? nil : id
    }

    func dismissTrustFlow() {
        showTrustFlow = false
        trustFlowResponse = nil
    }
}
