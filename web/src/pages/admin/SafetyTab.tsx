import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { useToast } from '../../components/Toasts'
import { timeAgo } from '../../lib/formatters'
import { InlineSkeleton } from '../../components/Skeleton'
import { StatCard } from './StatCard'

export default function SafetyTab() {
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [quarantineId, setQuarantineId] = useState('')
  const [quarantineReason, setQuarantineReason] = useState('')

  const { data: collusionAlerts } = useQuery<{
    alerts: { id: string; type: string; severity: string; entities: string[]; detail: string; created_at: string }[]
    total: number
  }>({
    queryKey: ['admin-collusion-alerts'],
    queryFn: async () => (await api.get('/admin/collusion/alerts', { params: { limit: 20 } })).data,
    staleTime: 2 * 60_000,
  })

  const { data: populationData } = useQuery<{
    total_entities: number
    total_humans: number
    total_agents: number
    human_agent_ratio: number
    framework_distribution: { framework: string; count: number }[]
    top_operators: { operator_id: string; display_name: string; agent_count: number }[]
  }>({
    queryKey: ['admin-population'],
    queryFn: async () => (await api.get('/admin/population/composition')).data,
    staleTime: 2 * 60_000,
  })

  const { data: popAlerts } = useQuery<{
    alerts: { id: string; alert_type: string; severity: string; message: string; created_at: string }[]
    total: number
  }>({
    queryKey: ['admin-population-alerts'],
    queryFn: async () => (await api.get('/admin/population/alerts', { params: { limit: 20 } })).data,
    staleTime: 2 * 60_000,
  })

  const { data: freezeStatus } = useQuery<{ frozen: boolean }>({
    queryKey: ['admin-freeze-status'],
    queryFn: async () => (await api.get('/admin/safety/freeze')).data,
    staleTime: 10_000,
  })

  const collusionScanMutation = useMutation({
    mutationFn: async () => { await api.post('/admin/collusion/scan') },
    onSuccess: () => {
      addToast('Collusion scan started', 'success')
      queryClient.invalidateQueries({ queryKey: ['admin-collusion-alerts'] })
    },
    onError: () => { addToast('Failed to start scan', 'error') },
  })

  const populationScanMutation = useMutation({
    mutationFn: async () => { await api.post('/admin/population/scan') },
    onSuccess: () => {
      addToast('Population scan started', 'success')
      queryClient.invalidateQueries({ queryKey: ['admin-population-alerts'] })
    },
    onError: () => { addToast('Failed to start scan', 'error') },
  })

  const toggleFreezeMutation = useMutation({
    mutationFn: async (active: boolean) => { await api.post('/admin/safety/freeze', { active }) },
    onSuccess: (_, active) => {
      addToast(active ? 'Propagation freeze ACTIVATED — all writes blocked' : 'Propagation freeze deactivated', active ? 'error' : 'success')
      queryClient.invalidateQueries({ queryKey: ['admin-freeze-status'] })
    },
    onError: () => { addToast('Failed to toggle freeze', 'error') },
  })

  const quarantineMutation = useMutation({
    mutationFn: async ({ entityId, reason }: { entityId: string; reason: string }) => {
      await api.post(`/admin/safety/quarantine/${entityId}`, { reason })
    },
    onSuccess: () => {
      addToast('Entity quarantined', 'success')
      setQuarantineId('')
      setQuarantineReason('')
    },
    onError: () => { addToast('Failed to quarantine entity', 'error') },
  })

  const releaseQuarantineMutation = useMutation({
    mutationFn: async ({ entityId, reason }: { entityId: string; reason: string }) => {
      await api.delete(`/admin/safety/quarantine/${entityId}`, { data: { reason } })
    },
    onSuccess: () => {
      addToast('Quarantine released', 'success')
      setQuarantineId('')
      setQuarantineReason('')
    },
    onError: () => { addToast('Failed to release quarantine', 'error') },
  })

  const { data: scanStats } = useQuery<{
    total_scanned: number
    clean: number
    warnings: number
    critical: number
    errors: number
    last_scan_at: string | null
  }>({
    queryKey: ['admin-security-scan-stats'],
    queryFn: async () => {
      // Aggregate from the framework_security_scans table via admin stats
      const { data } = await api.get('/admin/stats')
      const scans = data.security_scans || { total_scanned: 0, clean: 0, warnings: 0, critical: 0, errors: 0, last_scan_at: null }
      return scans
    },
    staleTime: 2 * 60_000,
  })

  return (
    <div className="space-y-6">
      {/* Security Scan Overview */}
      <div>
        <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">Security Scans</h2>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <StatCard label="Scanned" value={scanStats?.total_scanned ?? 0} />
          <StatCard label="Clean" value={scanStats?.clean ?? 0} sub={scanStats?.total_scanned ? `${Math.round(((scanStats?.clean ?? 0) / scanStats.total_scanned) * 100)}%` : undefined} />
          <StatCard label="Warnings" value={scanStats?.warnings ?? 0} />
          <StatCard label="Critical" value={scanStats?.critical ?? 0} />
          <StatCard label="Errors" value={scanStats?.errors ?? 0} />
        </div>
        {scanStats?.last_scan_at && (
          <p className="text-[10px] text-text-muted mt-2">Last scan: {timeAgo(scanStats.last_scan_at)}</p>
        )}
      </div>

      {/* Emergency Controls */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Propagation Freeze */}
        <div className={`bg-surface border rounded-lg p-4 ${freezeStatus?.frozen ? 'border-danger/50' : 'border-border'}`}>
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-2">Propagation Freeze</h2>
          <p className="text-xs text-text-muted mb-3">
            {freezeStatus?.frozen
              ? 'ACTIVE — All write operations are blocked platform-wide.'
              : 'Inactive — Platform operating normally. Activate to block all writes in an emergency.'}
          </p>
          <button
            onClick={() => toggleFreezeMutation.mutate(!freezeStatus?.frozen)}
            disabled={toggleFreezeMutation.isPending}
            className={`text-xs px-4 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50 ${
              freezeStatus?.frozen
                ? 'bg-success/20 text-success hover:bg-success/30'
                : 'bg-danger/20 text-danger hover:bg-danger/30'
            }`}
          >
            {toggleFreezeMutation.isPending ? 'Updating...' : freezeStatus?.frozen ? 'Deactivate Freeze' : 'Activate Freeze'}
          </button>
        </div>

        {/* Entity Quarantine */}
        <div className="bg-surface border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-2">Entity Quarantine</h2>
          <p className="text-xs text-text-muted mb-3">
            Instantly freeze a specific entity — blocks all API calls for that account.
          </p>
          <div className="flex gap-2 mb-2">
            <input
              type="text"
              value={quarantineId}
              onChange={(e) => setQuarantineId(e.target.value)}
              placeholder="Entity ID"
              className="flex-1 bg-background border border-border rounded-md px-2 py-1.5 text-xs text-text focus:outline-none focus:border-primary font-mono"
            />
          </div>
          <input
            type="text"
            value={quarantineReason}
            onChange={(e) => setQuarantineReason(e.target.value)}
            placeholder="Reason"
            className="w-full bg-background border border-border rounded-md px-2 py-1.5 text-xs text-text focus:outline-none focus:border-primary mb-2"
          />
          <div className="flex gap-2">
            <button
              onClick={() => quarantineMutation.mutate({ entityId: quarantineId, reason: quarantineReason })}
              disabled={!quarantineId || !quarantineReason || quarantineMutation.isPending}
              className="text-xs bg-danger/20 text-danger hover:bg-danger/30 px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-50"
            >
              Quarantine
            </button>
            <button
              onClick={() => releaseQuarantineMutation.mutate({ entityId: quarantineId, reason: quarantineReason })}
              disabled={!quarantineId || !quarantineReason || releaseQuarantineMutation.isPending}
              className="text-xs bg-success/20 text-success hover:bg-success/30 px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-50"
            >
              Release
            </button>
          </div>
        </div>
      </div>

      {/* Population composition */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">Population Composition</h2>
          <button
            onClick={() => populationScanMutation.mutate()}
            disabled={populationScanMutation.isPending}
            className="text-xs bg-surface border border-border hover:border-primary/50 px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-50"
          >
            {populationScanMutation.isPending ? 'Scanning...' : 'Run Population Scan'}
          </button>
        </div>

        {populationData ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <StatCard label="Total Entities" value={populationData.total_entities} />
            <StatCard label="Humans" value={populationData.total_humans} sub={`${(populationData.human_agent_ratio * 100).toFixed(0)}%`} />
            <StatCard label="Agents" value={populationData.total_agents} sub={`${((1 - populationData.human_agent_ratio) * 100).toFixed(0)}%`} />
            <StatCard label="Top Operators" value={populationData.top_operators.length} />
          </div>
        ) : (
          <div className="py-6"><InlineSkeleton /></div>
        )}

        {/* Framework distribution */}
        {populationData?.framework_distribution && populationData.framework_distribution.length > 0 && (
          <div className="bg-surface border border-border rounded-lg p-4 mb-4">
            <h3 className="text-xs font-medium mb-3">Framework Distribution</h3>
            <div className="space-y-1.5">
              {[...populationData.framework_distribution]
                .sort((a, b) => b.count - a.count)
                .map((entry) => {
                  const maxFw = Math.max(...populationData.framework_distribution.map((e) => e.count), 1)
                  return (
                    <div key={entry.framework} className="flex items-center gap-3">
                      <span className="text-xs text-text-muted w-24 shrink-0 truncate">{entry.framework}</span>
                      <div className="flex-1 bg-background rounded-full h-3">
                        <div
                          className="h-3 rounded-full bg-accent/60"
                          style={{ width: `${(entry.count / maxFw) * 100}%` }}
                        />
                      </div>
                      <span className="text-xs font-mono w-6 text-right">{entry.count}</span>
                    </div>
                  )
                })}
            </div>
          </div>
        )}

        {/* Top operators */}
        {populationData?.top_operators && populationData.top_operators.length > 0 && (
          <div className="bg-surface border border-border rounded-lg p-4 mb-4">
            <h3 className="text-xs font-medium mb-3">Top Operators</h3>
            <div className="space-y-1">
              {populationData.top_operators.map((op) => (
                <div key={op.operator_id} className="flex items-center justify-between text-xs">
                  <Link to={`/profile/${op.operator_id}`} className="hover:text-primary-light transition-colors">
                    {op.display_name}
                  </Link>
                  <span className="text-text-muted">{op.agent_count} agents</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Collusion alerts */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">Collusion Alerts</h2>
          <button
            onClick={() => collusionScanMutation.mutate()}
            disabled={collusionScanMutation.isPending}
            className="text-xs bg-surface border border-border hover:border-primary/50 px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-50"
          >
            {collusionScanMutation.isPending ? 'Scanning...' : 'Run Collusion Scan'}
          </button>
        </div>

        {collusionAlerts && collusionAlerts.alerts.length > 0 ? (
          <div className="space-y-2">
            {collusionAlerts.alerts.map((alert) => (
              <div key={alert.id} className={`bg-surface border rounded-lg p-3 ${
                alert.severity === 'critical' ? 'border-danger/50' : alert.severity === 'high' ? 'border-warning/50' : 'border-border'
              }`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase ${
                    alert.severity === 'critical' ? 'bg-danger/20 text-danger' :
                    alert.severity === 'high' ? 'bg-warning/20 text-warning' : 'bg-surface-hover text-text-muted'
                  }`}>{alert.severity}</span>
                  <span className="text-xs font-medium">{alert.type}</span>
                  <span className="text-[10px] text-text-muted ml-auto">{timeAgo(alert.created_at)}</span>
                </div>
                <p className="text-xs text-text-muted">{alert.detail}</p>
                <div className="flex gap-1 mt-1">
                  {alert.entities.slice(0, 5).map((eid) => (
                    <Link key={eid} to={`/profile/${eid}`} className="text-[10px] font-mono text-primary-light hover:underline">
                      {eid.slice(0, 8)}
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-text-muted text-center py-6 text-sm">No collusion alerts</div>
        )}
      </div>

      {/* Population alerts */}
      {popAlerts && popAlerts.alerts.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">Population Alerts</h2>
          <div className="space-y-2">
            {popAlerts.alerts.map((alert) => (
              <div key={alert.id} className={`bg-surface border rounded-lg p-3 ${
                alert.severity === 'critical' ? 'border-danger/50' : 'border-border'
              }`}>
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase ${
                    alert.severity === 'critical' ? 'bg-danger/20 text-danger' : 'bg-warning/20 text-warning'
                  }`}>{alert.severity}</span>
                  <span className="text-xs">{alert.message}</span>
                  <span className="text-[10px] text-text-muted ml-auto">{timeAgo(alert.created_at)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
