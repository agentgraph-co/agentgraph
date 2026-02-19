import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'

interface EvolutionRecord {
  id: string
  entity_id: string
  version: string
  change_type: string
  change_summary: string
  capabilities_snapshot: string[]
  risk_tier: number
  approval_status: string
  created_at: string
}

const CHANGE_TYPE_COLORS: Record<string, string> = {
  initial: 'bg-success/20 text-success',
  minor: 'bg-accent/20 text-accent',
  major: 'bg-warning/20 text-warning',
  breaking: 'bg-danger/20 text-danger',
  fork: 'bg-primary/20 text-primary-light',
}

const RISK_LABELS: Record<number, { label: string; color: string }> = {
  1: { label: 'Low', color: 'text-success' },
  2: { label: 'Medium', color: 'text-warning' },
  3: { label: 'High', color: 'text-danger' },
}

export default function EvolutionTimeline({ entityId }: { entityId: string }) {
  const { data, isLoading } = useQuery<{ records: EvolutionRecord[]; count: number }>({
    queryKey: ['evolution', entityId],
    queryFn: async () => {
      const { data } = await api.get(`/evolution/${entityId}`)
      return data
    },
  })

  if (isLoading) {
    return <div className="text-text-muted text-sm">Loading evolution history...</div>
  }

  if (!data || data.count === 0) {
    return null
  }

  return (
    <div className="mt-6">
      <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
        Evolution Timeline ({data.count} versions)
      </h2>
      <div className="relative">
        {/* Vertical line */}
        <div className="absolute left-3 top-2 bottom-2 w-px bg-border" />

        <div className="space-y-4">
          {data.records.map((record, i) => {
            const risk = RISK_LABELS[record.risk_tier] || RISK_LABELS[1]
            return (
              <div key={record.id} className="relative flex gap-4 pl-8">
                {/* Dot */}
                <div className={`absolute left-1.5 top-2 w-3 h-3 rounded-full border-2 border-background ${
                  i === 0 ? 'bg-primary' : 'bg-border'
                }`} />

                <div className="bg-surface border border-border rounded-lg p-3 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium">v{record.version}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${
                      CHANGE_TYPE_COLORS[record.change_type] || 'bg-surface-hover text-text-muted'
                    }`}>
                      {record.change_type}
                    </span>
                    <span className={`text-[10px] ${risk.color}`}>
                      Risk: {risk.label}
                    </span>
                    <span className="text-[10px] text-text-muted ml-auto">
                      {new Date(record.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <p className="text-xs text-text-muted">{record.change_summary}</p>
                  {record.capabilities_snapshot.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {record.capabilities_snapshot.map((cap, j) => (
                        <span key={j} className="text-[10px] px-1.5 py-0.5 bg-primary/10 text-primary-light rounded">
                          {cap}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
