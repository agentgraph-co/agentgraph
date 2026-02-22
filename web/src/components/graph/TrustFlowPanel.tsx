/**
 * Trust attestation chain overlay — side panel showing the attestation
 * tree from /graph/trust-flow/{id}. Displays who attests trust and how
 * it propagates through the network.
 */
import { useTrustFlow } from '../../hooks/useGraphData'
import type { TrustFlowAttestation } from '../../hooks/useGraphData'

interface TrustFlowPanelProps {
  entityId: string | null
  onClose: () => void
}

function AttestationNode({ att, depth }: { att: TrustFlowAttestation; depth: number }) {
  return (
    <div style={{ marginLeft: depth * 12 }}>
      <div className="flex items-center gap-1.5 py-1">
        {/* Connector line */}
        {depth > 0 && (
          <span className="text-border text-xs">{'-->'}</span>
        )}

        <div className="flex items-center gap-1.5 min-w-0 flex-1">
          <span className="text-xs truncate">{att.attester_name}</span>
          <span className="px-1 py-0.5 rounded text-[9px] bg-accent/10 text-accent shrink-0">
            {att.attestation_type}
          </span>
          <span className="text-[10px] text-text-muted shrink-0">
            w:{att.weight.toFixed(2)}
          </span>
        </div>
      </div>

      {/* Recursive children */}
      {att.children.map((child) => (
        <AttestationNode
          key={child.attester_id}
          att={child}
          depth={depth + 1}
        />
      ))}
    </div>
  )
}

export default function TrustFlowPanel({ entityId, onClose }: TrustFlowPanelProps) {
  const { data, isLoading, isError } = useTrustFlow(entityId)

  return (
    <div className="glass-strong rounded-lg p-3 shadow-lg w-72 max-h-[70vh] overflow-auto">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
          Trust Flow
        </h3>
        <button
          onClick={onClose}
          className="text-text-muted hover:text-text text-xs cursor-pointer"
          aria-label="Close trust flow panel"
        >
          x
        </button>
      </div>

      {isLoading && (
        <div className="text-[10px] text-text-muted py-4 text-center">
          Loading trust chain...
        </div>
      )}

      {isError && (
        <div className="text-[10px] text-danger py-2">
          Failed to load trust flow data
        </div>
      )}

      {data && (
        <>
          {/* Root entity */}
          <div className="flex items-center gap-2 mb-2 pb-2 border-b border-border/50">
            <span className="text-xs font-medium">Entity</span>
            <span className="text-[10px] text-text-muted font-mono truncate">{data.entity_id.slice(0, 12)}...</span>
            {data.trust_score != null && (
              <span className="ml-auto text-xs text-primary-light font-medium">
                {(data.trust_score * 100).toFixed(0)}%
              </span>
            )}
          </div>

          {/* Attestation tree */}
          {data.attestations.length === 0 ? (
            <div className="text-[10px] text-text-muted py-2 text-center">
              No attestations found
            </div>
          ) : (
            <div className="space-y-0.5">
              <div className="text-[10px] text-text-muted mb-1">
                {data.attestations.length} direct attestation{data.attestations.length !== 1 ? 's' : ''}
              </div>
              {data.attestations.map((att) => (
                <AttestationNode key={att.attester_id} att={att} depth={0} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
