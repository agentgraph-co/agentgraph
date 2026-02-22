// GraphView — SpriteKit force-directed trust network visualization
// Upgraded from Canvas radial layout to SpriteKit force simulation

import SwiftUI

struct GraphView: View {
    @Environment(AuthViewModel.self) private var auth
    @State private var viewModel = ForceGraphViewModel()

    var body: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                if viewModel.isLoading && viewModel.nodes.isEmpty {
                    LoadingStateView(state: .loading)
                } else if let error = viewModel.error, viewModel.nodes.isEmpty {
                    LoadingStateView(state: .error(message: error, retry: {
                        await viewModel.loadRichGraph(centerId: auth.currentUser?.id)
                    }))
                } else {
                    // SpriteKit force-directed graph
                    ForceGraphView(
                        nodes: viewModel.nodes,
                        edges: viewModel.edges,
                        onNodeTap: { nodeId in
                            viewModel.selectNode(nodeId)
                        },
                        onNodeLongPress: { nodeId in
                            Task {
                                await viewModel.loadTrustFlow(entityId: nodeId)
                            }
                        },
                        selectedNodeId: viewModel.selectedNodeId
                    )
                    .ignoresSafeArea()

                    // Overlay controls
                    VStack {
                        // Cluster legend (top-left)
                        HStack {
                            ClusterLegendView(
                                clusters: viewModel.clusters,
                                isVisible: $viewModel.showClusters
                            )
                            Spacer()
                        }
                        .padding(.horizontal, AGSpacing.sm)
                        .padding(.top, AGSpacing.sm)

                        Spacer()

                        // Selected node info bar
                        if let selectedId = viewModel.selectedNodeId,
                           let selectedNode = viewModel.nodes.first(where: { $0.id == selectedId }) {
                            selectedNodeBar(selectedNode)
                                .transition(.move(edge: .bottom).combined(with: .opacity))
                        }

                        // Stats bar
                        statsBar
                    }
                }
            }
            .navigationTitle("Graph")
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Menu {
                        Button {
                            Task { await viewModel.loadRichGraph(centerId: auth.currentUser?.id) }
                        } label: {
                            Label("Reload", systemImage: "arrow.clockwise")
                        }
                        Button {
                            Task {
                                if let id = auth.currentUser?.id {
                                    await viewModel.loadRichGraph(centerId: id)
                                }
                            }
                        } label: {
                            Label("Center on Me", systemImage: "person.circle")
                        }
                        Button {
                            withAnimation {
                                viewModel.showClusters.toggle()
                            }
                        } label: {
                            Label(
                                viewModel.showClusters ? "Hide Clusters" : "Show Clusters",
                                systemImage: viewModel.showClusters ? "eye.slash" : "eye"
                            )
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                    .tint(.agPrimary)
                }
            }
            .navigationDestination(for: String.self) { nodeId in
                if let uuid = UUID(uuidString: nodeId) {
                    ProfileDetailView(entityId: uuid)
                }
            }
            .sheet(isPresented: $viewModel.showTrustFlow) {
                if let trustFlow = viewModel.trustFlowResponse {
                    TrustFlowSheet(
                        trustFlow: trustFlow,
                        onDismiss: {
                            viewModel.dismissTrustFlow()
                        },
                        onNodeTap: { nodeId in
                            viewModel.dismissTrustFlow()
                            viewModel.selectNode(nodeId)
                        }
                    )
                    .presentationDetents([.medium, .large])
                    .presentationDragIndicator(.visible)
                }
            }
            .task {
                await viewModel.loadRichGraph(centerId: auth.currentUser?.id)
            }
        }
    }

    // MARK: - Selected Node Bar

    private func selectedNodeBar(_ node: ForceNode) -> some View {
        NavigationLink(value: node.id) {
            HStack(spacing: AGSpacing.md) {
                // Node icon
                ZStack {
                    Circle()
                        .fill(nodeColor(node).opacity(0.2))
                        .frame(width: 36, height: 36)

                    Circle()
                        .fill(nodeColor(node))
                        .frame(width: 28, height: 28)

                    Image(systemName: node.type == "human" ? "person.fill" : "cpu")
                        .font(.system(size: 12))
                        .foregroundStyle(.white)
                }

                VStack(alignment: .leading, spacing: 2) {
                    Text(node.label)
                        .font(AGTypography.sm)
                        .fontWeight(.medium)
                        .foregroundStyle(Color.agText)

                    HStack(spacing: AGSpacing.sm) {
                        Text(String(format: "Trust: %.2f", node.trustScore))
                            .font(AGTypography.xs)
                            .foregroundStyle(trustColor(node.trustScore))

                        Text("\(node.connections.count) connections")
                            .font(AGTypography.xs)
                            .foregroundStyle(Color.agMuted)
                    }
                }

                Spacer()

                Image(systemName: "chevron.right")
                    .font(AGTypography.xs)
                    .foregroundStyle(Color.agMuted)
            }
            .padding(AGSpacing.md)
            .glassCard(padding: 0)
        }
        .buttonStyle(.plain)
        .padding(.horizontal, AGSpacing.base)
        .padding(.bottom, AGSpacing.xs)
    }

    // MARK: - Stats Bar

    private var statsBar: some View {
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
                    let scores = viewModel.nodes.map(\.trustScore)
                    let avgTrust = scores.isEmpty ? 0 : scores.reduce(0, +) / Double(scores.count)
                    Text(String(format: "%.2f", avgTrust))
                        .font(AGTypography.lg)
                        .fontWeight(.bold)
                        .foregroundStyle(Color.agSuccess)
                    Text("Avg Trust")
                        .font(AGTypography.xs)
                        .foregroundStyle(Color.agMuted)
                }
                VStack(spacing: 2) {
                    Text("\(viewModel.clusters.count)")
                        .font(AGTypography.lg)
                        .fontWeight(.bold)
                        .foregroundStyle(Color.agAccent)
                    Text("Clusters")
                        .font(AGTypography.xs)
                        .foregroundStyle(Color.agMuted)
                }
            }
            .frame(maxWidth: .infinity)
        }
        .padding(.horizontal, AGSpacing.base)
        .padding(.bottom, AGSpacing.sm)
    }

    // MARK: - Helpers

    private func nodeColor(_ node: ForceNode) -> Color {
        let c = ForceGraphViewModel.colorForCluster(node.clusterId)
        return Color(red: c.red, green: c.green, blue: c.blue)
    }

    private func trustColor(_ trust: Double) -> Color {
        if trust >= 0.8 { return .agSuccess }
        if trust >= 0.5 { return .agWarning }
        return .agDanger
    }
}
