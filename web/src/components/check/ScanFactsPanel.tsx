/**
 * ScanFactsPanel — surfaces the scan outputs that previously had no UI:
 * positive security signals, the recommended gateway limits (an actionable output),
 * scan metadata (files/language/hygiene), and false-positive-suppression transparency.
 */
import type { RecommendedLimits, ScanMetadata } from '../../types/scan'

interface Props {
  positiveSignals?: string[]
  trustTier?: string
  limits?: RecommendedLimits
  metadata?: ScanMetadata
  suppressedLines?: number
}

const TIER_LABEL: Record<string, string> = {
  verified: 'Verified',
  trusted: 'Trusted',
  standard: 'Standard',
  minimal: 'Minimal',
  restricted: 'Restricted',
  blocked: 'Blocked',
}

export default function ScanFactsPanel({
  positiveSignals,
  trustTier,
  limits,
  metadata,
  suppressedLines,
}: Props) {
  const signals = positiveSignals ?? []
  const hasLimits =
    limits &&
    (limits.requests_per_minute != null ||
      limits.max_tokens_per_call != null ||
      limits.require_user_confirmation)

  if (!signals.length && !hasLimits && !metadata && !suppressedLines) return null

  return (
    <div className="rounded-lg border border-border bg-surface p-4 space-y-4">
      {/* Positive signals */}
      {signals.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
            Good practices detected
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {signals.map((s) => (
              <span
                key={s}
                className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-[11px] text-success"
              >
                ✓ {s}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Recommended gateway limits */}
      {hasLimits && (
        <div>
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
            Recommended limits
            {trustTier && TIER_LABEL[trustTier] ? ` · ${TIER_LABEL[trustTier]} tier` : ''}
          </h3>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
            {limits!.requests_per_minute != null && (
              <span>{limits!.requests_per_minute} req/min</span>
            )}
            {limits!.max_tokens_per_call != null && (
              <span>{limits!.max_tokens_per_call.toLocaleString()} tokens/call</span>
            )}
            <span>
              {limits!.require_user_confirmation
                ? 'User confirmation required'
                : 'No confirmation required'}
            </span>
          </div>
        </div>
      )}

      {/* Scan metadata */}
      {metadata && (
        <div>
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
            Scan facts
          </h3>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
            <span>{metadata.files_scanned} files scanned</span>
            {metadata.primary_language && <span>{metadata.primary_language}</span>}
            {metadata.is_mcp_server && <span>MCP server</span>}
            <span className={metadata.has_readme ? 'text-success' : ''}>
              {metadata.has_readme ? '✓' : '✕'} README
            </span>
            <span className={metadata.has_license ? 'text-success' : ''}>
              {metadata.has_license ? '✓' : '✕'} License
            </span>
            <span className={metadata.has_tests ? 'text-success' : ''}>
              {metadata.has_tests ? '✓' : '✕'} Tests
            </span>
          </div>
        </div>
      )}

      {suppressedLines != null && suppressedLines > 0 && (
        <p className="text-[11px] text-text-muted">
          {suppressedLines} line{suppressedLines !== 1 ? 's' : ''} marked{' '}
          <code className="font-mono">ag-scan:ignore</code> and excluded from findings.
        </p>
      )}
    </div>
  )
}
