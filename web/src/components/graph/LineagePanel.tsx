/**
 * Evolution lineage tree overlay — side panel showing the fork tree
 * from /graph/lineage-tree/{id}. Displays how agents were forked
 * from one another and their version history.
 */
import { useLineageTree } from '../../hooks/useGraphData'
import type { LineageNode } from '../../hooks/useGraphData'
import { Link } from 'react-router-dom'

interface LineagePanelProps {
  entityId: string | null
  onClose: () => void
}

function LineageTreeNode({ node, depth }: { node: LineageNode; depth: number }) {
  return (
    <div style={{ marginLeft: depth * 14 }}>
      <div className="flex items-center gap-1.5 py-1">
        {/* Connector */}
        {depth > 0 && (
          <span className="text-border text-[10px]">|--</span>
        )}

        <Link
          to={`/profile/${node.entity_id}`}
          className="text-xs hover:text-primary-light transition-colors truncate"
        >
          {node.entity_name}
        </Link>

        {node.version && (
          <span className="px-1 py-0.5 rounded text-[9px] bg-surface-elevated text-text-muted shrink-0">
            v{node.version}
          </span>
        )}
      </div>

      {/* Recursive children (forks) */}
      {node.children.map((child) => (
        <LineageTreeNode
          key={child.entity_id}
          node={child}
          depth={depth + 1}
        />
      ))}
    </div>
  )
}

export default function LineagePanel({ entityId, onClose }: LineagePanelProps) {
  const { data, isLoading, isError } = useLineageTree(entityId)

  return (
    <div className="glass-strong rounded-lg p-3 shadow-lg w-72 max-h-[70vh] overflow-auto">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
          Evolution Lineage
        </h3>
        <button
          onClick={onClose}
          className="text-text-muted hover:text-text text-xs cursor-pointer"
          aria-label="Close lineage panel"
        >
          x
        </button>
      </div>

      {isLoading && (
        <div className="text-[10px] text-text-muted py-4 text-center">
          Loading lineage tree...
        </div>
      )}

      {isError && (
        <div className="text-[10px] text-danger py-2">
          Failed to load lineage data
        </div>
      )}

      {data && (
        <>
          {/* Root entity */}
          <div className="mb-2 pb-2 border-b border-border/50">
            <div className="flex items-center gap-2">
              <Link
                to={`/profile/${data.entity_id}`}
                className="text-xs font-medium hover:text-primary-light transition-colors"
              >
                {data.entity_name}
              </Link>
              {data.version && (
                <span className="px-1 py-0.5 rounded text-[9px] bg-primary/10 text-primary-light">
                  v{data.version}
                </span>
              )}
            </div>
            <div className="text-[10px] text-text-muted mt-0.5">Root entity</div>
          </div>

          {/* Fork tree */}
          {data.children.length === 0 ? (
            <div className="text-[10px] text-text-muted py-2 text-center">
              No forks found
            </div>
          ) : (
            <div className="space-y-0.5">
              <div className="text-[10px] text-text-muted mb-1">
                {data.children.length} direct fork{data.children.length !== 1 ? 's' : ''}
              </div>
              {data.children.map((child) => (
                <LineageTreeNode key={child.entity_id} node={child} depth={0} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
