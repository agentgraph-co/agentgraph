// ClusterLegendView — Color-coded cluster legend overlay for the graph

import SwiftUI

struct ClusterLegendView: View {
    let clusters: [ClusterInfo]
    @Binding var isVisible: Bool

    var body: some View {
        if isVisible && !clusters.isEmpty {
            VStack(alignment: .leading, spacing: AGSpacing.sm) {
                HStack {
                    Text("Clusters")
                        .font(AGTypography.sm)
                        .fontWeight(.semibold)
                        .foregroundStyle(Color.agText)

                    Spacer()

                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            isVisible = false
                        }
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(AGTypography.sm)
                            .foregroundStyle(Color.agMuted)
                    }
                }

                ForEach(clusters.prefix(10)) { cluster in
                    HStack(spacing: AGSpacing.sm) {
                        Circle()
                            .fill(clusterColor(cluster.clusterId))
                            .frame(width: 10, height: 10)

                        VStack(alignment: .leading, spacing: 0) {
                            Text("Cluster \(cluster.clusterId)")
                                .font(AGTypography.xs)
                                .foregroundStyle(Color.agText)

                            HStack(spacing: AGSpacing.xs) {
                                Text("\(cluster.memberCount)")
                                    .font(AGTypography.xs)
                                    .foregroundStyle(Color.agMuted)

                                Text(cluster.dominantType.capitalized)
                                    .font(AGTypography.xs)
                                    .foregroundStyle(Color.agMuted)

                                Text(String(format: "%.2f", cluster.avgTrust))
                                    .font(AGTypography.xs)
                                    .foregroundStyle(trustColor(cluster.avgTrust))
                            }
                        }
                    }
                }

                if clusters.count > 10 {
                    Text("+\(clusters.count - 10) more")
                        .font(AGTypography.xs)
                        .foregroundStyle(Color.agMuted)
                }
            }
            .padding(AGSpacing.md)
            .glassCard(padding: 0)
            .frame(maxWidth: 180)
            .transition(.opacity.combined(with: .move(edge: .leading)))
        }
    }

    private func clusterColor(_ clusterId: Int) -> Color {
        let c = ForceGraphViewModel.colorForCluster(clusterId)
        return Color(red: c.red, green: c.green, blue: c.blue)
    }

    private func trustColor(_ trust: Double) -> Color {
        if trust >= 0.8 { return .agSuccess }
        if trust >= 0.5 { return .agWarning }
        return .agDanger
    }
}
