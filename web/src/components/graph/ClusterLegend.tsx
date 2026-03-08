/**
 * Cluster color legend — shows cluster name/id, color swatch, member count.
 * Clicking a cluster highlights/filters nodes to that cluster.
 */
import type { ClusterInfo } from '../../hooks/useGraphData'
import { clusterColorThemed, UNCLUSTERED_COLOR, UNCLUSTERED_COLOR_LIGHT } from '../../lib/graphTheme'
import { useTheme } from '../../hooks/useTheme'

interface ClusterLegendProps {
  clusters: ClusterInfo[]
  activeCluster: number | null
  onClusterClick: (clusterId: number | null) => void
}

export default function ClusterLegend({ clusters, activeCluster, onClusterClick }: ClusterLegendProps) {
  const { theme } = useTheme()
  if (clusters.length === 0) return null

  return (
    <div className="glass-strong rounded-lg p-3 shadow-lg w-52 max-h-[50vh] overflow-auto">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">
        Clusters
      </h3>

      {/* All / reset button */}
      <button
        onClick={() => onClusterClick(null)}
        className={`w-full flex items-center gap-2 px-2 py-1 rounded text-xs transition-colors cursor-pointer mb-1 ${
          activeCluster === null
            ? 'bg-primary/10 text-primary-light'
            : 'text-text-muted hover:text-text'
        }`}
      >
        <span
          className="w-2.5 h-2.5 rounded-full shrink-0 border border-border"
          style={{ background: theme === 'light' ? UNCLUSTERED_COLOR_LIGHT : UNCLUSTERED_COLOR }}
        />
        <span className="flex-1 text-left">All clusters</span>
      </button>

      {/* Cluster list */}
      <div className="space-y-0.5">
        {clusters.map((c) => (
          <button
            key={c.cluster_id}
            onClick={() => onClusterClick(activeCluster === c.cluster_id ? null : c.cluster_id)}
            className={`w-full flex items-center gap-2 px-2 py-1 rounded text-xs transition-colors cursor-pointer ${
              activeCluster === c.cluster_id
                ? 'bg-primary/10 text-primary-light'
                : 'text-text-muted hover:text-text'
            }`}
          >
            <span
              className="w-2.5 h-2.5 rounded-full shrink-0"
              style={{ background: clusterColorThemed(c.cluster_id, theme) }}
            />
            <span className="flex-1 text-left truncate">
              Cluster {c.cluster_id}
            </span>
            <span className="text-[10px] text-text-muted shrink-0">
              {c.member_count}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
