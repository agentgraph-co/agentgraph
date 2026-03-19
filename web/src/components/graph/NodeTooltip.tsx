/**
 * Rich hover card for graph nodes — shows a mini-profile with
 * avatar, display name, entity type, trust score, cluster, and action buttons.
 */
import { Link } from 'react-router-dom'
import type { GraphNode } from '../../hooks/useGraphData'
import { clusterColor } from '../../lib/graphTheme'

interface NodeTooltipProps {
  node: GraphNode | null
  position: { x: number; y: number }
  onViewEgoGraph?: (entityId: string) => void
  onViewTrustFlow?: (entityId: string) => void
}

export default function NodeTooltip({ node, position, onViewEgoGraph, onViewTrustFlow }: NodeTooltipProps) {
  if (!node) return null

  const trustPercent = node.trust_score != null ? (node.trust_score * 100).toFixed(0) : null

  return (
    <div
      className="absolute z-50 pointer-events-none"
      style={{ left: position.x + 12, top: position.y - 10 }}
    >
      <div className="glass-strong rounded-lg p-3 shadow-xl min-w-[200px] max-w-[260px]">
        {/* Header */}
        <div className="flex items-center gap-2.5 mb-2">
          {node.avatar_url ? (
            <img
              src={node.avatar_url}
              alt={node.label}
              className="w-8 h-8 rounded-full border border-border object-cover"
            />
          ) : (
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border border-border ${
              node.type === 'agent' ? 'bg-blue-400/20 text-blue-400' : 'bg-success/20 text-success'
            }`}>
              {node.label.charAt(0).toUpperCase()}
            </div>
          )}
          <div className="min-w-0 flex-1">
            <p className="font-medium text-sm truncate">{node.label}</p>
            <div className="flex items-center gap-1.5">
              <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${
                node.type === 'agent' ? 'bg-blue-400/20 text-blue-400' : 'bg-success/20 text-success'
              }`}>
                {node.type}
              </span>
              {trustPercent != null && (
                <span className="text-[10px] text-text-muted">
                  Trust: {trustPercent}%
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Cluster */}
        {node.cluster_id != null && (
          <div className="flex items-center gap-1.5 mb-2 text-[10px] text-text-muted">
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ background: clusterColor(node.cluster_id) }}
            />
            <span>Cluster {node.cluster_id}</span>
          </div>
        )}

        {/* Actions — re-enable pointer events only for clickable buttons */}
        <div className="flex items-center gap-1.5 pt-1.5 border-t border-border/50 pointer-events-auto">
          <Link
            to={`/profile/${node.id}`}
            className="flex-1 text-center text-[10px] px-2 py-1 rounded bg-primary/10 text-primary-light hover:bg-primary/20 transition-colors"
          >
            Profile
          </Link>
          {onViewEgoGraph && (
            <button
              onClick={() => onViewEgoGraph(node.id)}
              className="flex-1 text-center text-[10px] px-2 py-1 rounded bg-surface-elevated text-text-muted hover:text-text transition-colors cursor-pointer"
            >
              Ego Graph
            </button>
          )}
          {onViewTrustFlow && (
            <button
              onClick={() => onViewTrustFlow(node.id)}
              className="flex-1 text-center text-[10px] px-2 py-1 rounded bg-surface-elevated text-text-muted hover:text-text transition-colors cursor-pointer"
            >
              Trust Flow
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
