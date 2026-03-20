import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import { timeAgo } from '../../lib/formatters'
import type { AuditLogEntry } from './types'

export default function AuditTab() {
  const { data: auditLogs } = useQuery<{ logs: AuditLogEntry[]; total: number }>({
    queryKey: ['admin-audit'],
    queryFn: async () => {
      const { data } = await api.get('/admin/audit-logs', { params: { limit: 50 } })
      return data
    },
    staleTime: 2 * 60_000,
  })

  return (
    <div>
      <div className="space-y-1">
        {auditLogs?.logs.map((log) => (
          <div
            key={log.id}
            className="bg-surface border border-border rounded px-3 py-2 flex items-center gap-3 text-xs"
          >
            <span className="text-text-muted shrink-0 w-20">{timeAgo(log.created_at)}</span>
            <span className="font-mono text-primary-light shrink-0">{log.action}</span>
            <span className="text-text-muted truncate">
              {log.resource_type && `${log.resource_type}`}
              {log.resource_id && ` #${log.resource_id.slice(0, 8)}`}
            </span>
            {log.entity_id && (
              <Link
                to={`/profile/${log.entity_id}`}
                className="text-text-muted hover:text-primary-light ml-auto shrink-0"
              >
                by #{log.entity_id.slice(0, 8)}
              </Link>
            )}
          </div>
        ))}
      </div>
      {auditLogs && auditLogs.logs.length === 0 && (
        <div className="text-text-muted text-center py-10">No audit logs</div>
      )}
    </div>
  )
}
