import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'

interface VerificationBadge {
  id: string
  entity_id: string
  badge_type: string
  issued_by: string | null
  issued_by_display_name: string | null
  proof_url: string | null
  expires_at: string | null
  is_active: boolean
  created_at: string
}

interface AuditRecordItem {
  id: string
  target_entity_id: string
  auditor_entity_id: string
  auditor_display_name: string
  audit_type: string
  result: string
  findings: Record<string, unknown> | null
  report_url: string | null
  created_at: string
}

export function BadgesSection({ entityId }: { entityId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['badges', entityId],
    queryFn: async () => {
      const resp = await api.get('/entities/' + entityId + '/badges')
      return resp.data as { badges: VerificationBadge[]; total: number }
    },
  })

  if (isLoading) return <div className="text-text-muted text-sm">Loading badges...</div>

  const badges = data?.badges || []
  if (badges.length === 0) {
    return <div className="text-text-muted text-sm">No verification badges yet.</div>
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
      {badges.map((badge) => (
        <div key={badge.id} className="p-3 rounded-lg border border-border bg-surface/50">
          <div className="text-sm font-medium capitalize">
            {badge.badge_type.replace(/_/g, ' ')}
          </div>
          {badge.issued_by_display_name && (
            <div className="text-xs text-text-muted">Issued by {badge.issued_by_display_name}</div>
          )}
          {badge.proof_url && (
            <a href={badge.proof_url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary-light underline">
              View Proof
            </a>
          )}
        </div>
      ))}
    </div>
  )
}

export function AuditHistorySection({ entityId }: { entityId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['audit-history', entityId],
    queryFn: async () => {
      const resp = await api.get('/entities/' + entityId + '/audit-history')
      return resp.data as { audit_records: AuditRecordItem[]; total: number }
    },
  })

  if (isLoading) return <div className="text-text-muted text-sm">Loading audit history...</div>

  const records = data?.audit_records || []
  if (records.length === 0) {
    return <div className="text-text-muted text-sm">No audit records yet.</div>
  }

  const resultColors: Record<string, string> = {
    pass: 'text-success',
    fail: 'text-danger',
    partial: 'text-warning',
  }

  return (
    <div className="space-y-2">
      {records.map((record) => (
        <div key={record.id} className="p-3 rounded-lg border border-border bg-surface/50">
          <div className="flex justify-between items-start">
            <div>
              <span className="text-sm font-medium capitalize">{record.audit_type}</span>
              <span className={"ml-2 text-sm font-semibold " + (resultColors[record.result] || "")}>
                {record.result.toUpperCase()}
              </span>
            </div>
            <span className="text-xs text-text-muted">
              {new Date(record.created_at).toLocaleDateString()}
            </span>
          </div>
          <div className="text-xs text-text-muted mt-1">Audited by {record.auditor_display_name}</div>
          {record.report_url && (
            <a href={record.report_url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary-light underline mt-1 inline-block">
              View Report
            </a>
          )}
        </div>
      ))}
    </div>
  )
}
