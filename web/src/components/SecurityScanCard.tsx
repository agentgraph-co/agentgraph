import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { useToast } from './Toasts'

interface ScanCategory {
  category: string
  count: number
  status: 'clear' | 'warning' | 'critical'
}

interface SecurityScanData {
  entity_id: string
  scan_result: 'clean' | 'warnings' | 'critical' | 'error' | 'pending'
  trust_score: number
  files_scanned: number
  categories: ScanCategory[]
  positive_signals: string[]
  total_findings: number
  critical_count: number
  high_count: number
  medium_count: number
  scanned_at: string | null
  repo: string | null
}

const STATUS_CONFIG = {
  clean: { label: 'Clean', color: 'text-success', bg: 'bg-success/10', icon: '\u2713' },
  warnings: { label: 'Warnings', color: 'text-warning', bg: 'bg-warning/10', icon: '\u26A0' },
  critical: { label: 'Critical', color: 'text-danger', bg: 'bg-danger/10', icon: '\u2717' },
  error: { label: 'Error', color: 'text-text-muted', bg: 'bg-surface-hover', icon: '?' },
  pending: { label: 'Pending', color: 'text-text-muted', bg: 'bg-surface-hover', icon: '\u2026' },
}

const CATEGORY_ICONS: Record<string, string> = {
  'Credential Theft': '\uD83D\uDD11',
  'Data Exfiltration': '\uD83D\uDCE1',
  'Unsafe Execution': '\u26A0\uFE0F',
  'Filesystem Access': '\uD83D\uDCC1',
  'Code Obfuscation': '\uD83D\uDD75\uFE0F',
}

const SCAN_CATEGORIES = [
  'Credential Theft',
  'Data Exfiltration',
  'Unsafe Execution',
  'Filesystem Access',
  'Code Obfuscation',
]

const PULSE_DELAYS = [
  'animate-scan-pulse',
  'animate-scan-pulse-d1',
  'animate-scan-pulse-d2',
  'animate-scan-pulse-d3',
  'animate-scan-pulse-d4',
]

function ScanningAnimation() {
  return (
    <div className="bg-surface border border-primary/30 rounded-lg p-4 relative overflow-hidden">
      {/* Sweep line */}
      <div
        className="absolute left-0 right-0 h-px animate-scan-sweep pointer-events-none"
        style={{
          background: 'linear-gradient(90deg, transparent 0%, var(--color-primary) 30%, var(--color-primary) 70%, transparent 100%)',
          boxShadow: '0 0 8px var(--color-primary-glow), 0 0 2px var(--color-primary)',
        }}
      />

      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
          Security Scan
        </h3>
        <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary-light animate-scan-counter">
          Scanning...
        </span>
      </div>

      {/* File counter */}
      <div className="flex items-center gap-3 mb-4">
        <div className="font-mono text-xs text-text-muted flex items-center gap-1.5">
          <span className="text-primary-light animate-scan-counter">&gt;</span>
          <span>Analyzing source files</span>
          <span className="animate-scan-pulse">...</span>
        </div>
      </div>

      {/* Category checklist */}
      <div className="space-y-2.5">
        {SCAN_CATEGORIES.map((cat, i) => (
          <div key={cat} className={`flex items-center gap-2 text-xs ${PULSE_DELAYS[i]}`}>
            <span className="w-3.5 h-3.5 rounded border border-border flex items-center justify-center text-[10px] text-text-muted">
              {CATEGORY_ICONS[cat] || '\uD83D\uDD0D'}
            </span>
            <span className="text-text-muted">{cat}</span>
            <span className="ml-auto font-mono text-[10px] text-text-muted">
              --
            </span>
          </div>
        ))}
      </div>

      {/* Bottom progress bar */}
      <div className="mt-4 h-0.5 bg-border/40 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{
            background: 'var(--color-primary)',
            animation: 'scan-sweep 2.5s ease-in-out infinite',
            width: '30%',
            position: 'relative',
          }}
        />
      </div>
    </div>
  )
}

export default function SecurityScanCard({
  entityId,
  canRescan = false,
  compact = false,
}: {
  entityId: string
  canRescan?: boolean
  compact?: boolean
}) {
  const queryClient = useQueryClient()
  const { addToast } = useToast()

  const { data: scan, isLoading } = useQuery<SecurityScanData>({
    queryKey: ['security-scan', entityId],
    queryFn: async () => (await api.get(`/bots/${entityId}/security-scan`)).data,
    staleTime: 5 * 60_000,
    refetchInterval: (query) => {
      const data = query.state.data as SecurityScanData | undefined
      // Poll every 3s while pending so we pick up results
      return data?.scan_result === 'pending' ? 3000 : false
    },
  })

  const rescanMutation = useMutation({
    mutationFn: async () => (await api.post(`/bots/${entityId}/security-scan`)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['security-scan', entityId] })
      addToast('Security scan triggered', 'success')
    },
    onError: () => addToast('Failed to trigger scan', 'error'),
  })

  const isScanning = rescanMutation.isPending || scan?.scan_result === 'pending'

  if (isLoading) {
    return (
      <div className="bg-surface border border-border rounded-lg p-4 animate-pulse">
        <div className="h-4 bg-background rounded w-32 mb-3" />
        <div className="h-3 bg-background rounded w-48" />
      </div>
    )
  }

  // Show scanning animation when pending or rescan in progress
  if (isScanning) {
    return <ScanningAnimation />
  }

  if (!scan) {
    if (compact) return null
    return (
      <div className="bg-surface border border-border rounded-lg p-4">
        <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-2">Security Scan</h3>
        <p className="text-xs text-text-muted">
          No security scan available for this agent.
        </p>
        {canRescan && (
          <button
            onClick={() => rescanMutation.mutate()}
            disabled={rescanMutation.isPending}
            className="mt-3 text-xs bg-primary/10 text-primary-light hover:bg-primary/20 px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-50"
          >
            {rescanMutation.isPending ? 'Scanning\u2026' : 'Run Scan'}
          </button>
        )}
      </div>
    )
  }

  const status = STATUS_CONFIG[scan.scan_result] || STATUS_CONFIG.error

  return (
    <div className={`bg-surface border rounded-lg p-4 ${
      scan.scan_result === 'critical' ? 'border-danger/40' :
      scan.scan_result === 'warnings' ? 'border-warning/40' :
      scan.scan_result === 'clean' ? 'border-success/40' : 'border-border'
    }`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider">Security Scan</h3>
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-0.5 rounded ${status.bg} ${status.color}`}>
            {status.icon} {status.label}
          </span>
          {canRescan && (
            <button
              onClick={() => rescanMutation.mutate()}
              disabled={rescanMutation.isPending}
              className="text-xs text-text-muted hover:text-primary-light transition-colors cursor-pointer disabled:opacity-50"
              title="Re-scan"
            >
              {rescanMutation.isPending ? '\u21BB' : '\u21BB'}
            </button>
          )}
        </div>
      </div>

      {/* Trust score + stats */}
      <div className="flex items-center gap-4 mb-4">
        <div className="text-center">
          <div className={`text-2xl font-bold ${
            scan.trust_score >= 70 ? 'text-success' :
            scan.trust_score >= 40 ? 'text-warning' : 'text-danger'
          }`}>
            {scan.trust_score}
          </div>
          <div className="text-[10px] text-text-muted uppercase">Trust Score</div>
        </div>
        <div className="flex-1 grid grid-cols-3 gap-2 text-center">
          <div>
            <div className="text-sm font-medium">{scan.files_scanned}</div>
            <div className="text-[10px] text-text-muted">Files</div>
          </div>
          <div>
            <div className="text-sm font-medium">{scan.total_findings}</div>
            <div className="text-[10px] text-text-muted">Findings</div>
          </div>
          <div>
            <div className={`text-sm font-medium ${scan.critical_count > 0 ? 'text-danger' : 'text-text'}`}>
              {scan.critical_count}
            </div>
            <div className="text-[10px] text-text-muted">Critical</div>
          </div>
        </div>
      </div>

      {/* Category breakdown */}
      {!compact && (
        <div className="space-y-1.5 mb-3">
          {scan.categories.map((cat) => (
            <div key={cat.category} className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-1.5">
                <span>{CATEGORY_ICONS[cat.category] || '\uD83D\uDD0D'}</span>
                <span className={cat.status === 'clear' ? 'text-text-muted' : 'text-text'}>
                  {cat.category}
                </span>
              </span>
              <span className={
                cat.status === 'critical' ? 'text-danger font-medium' :
                cat.status === 'warning' ? 'text-warning' :
                'text-success'
              }>
                {cat.count > 0 ? `${cat.count} finding${cat.count !== 1 ? 's' : ''}` : 'Clear'}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Positive signals */}
      {!compact && scan.positive_signals.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {scan.positive_signals.map((signal) => (
            <span key={signal} className="text-[10px] bg-success/10 text-success px-1.5 py-0.5 rounded">
              {signal}
            </span>
          ))}
        </div>
      )}

      {/* Footer */}
      {scan.scanned_at && (
        <div className="flex items-center justify-between text-[10px] text-text-muted pt-2 border-t border-border">
          <span>Scanned {new Date(scan.scanned_at).toLocaleDateString()}</span>
          {scan.repo && <span className="font-mono">{scan.repo}</span>}
        </div>
      )}
    </div>
  )
}
