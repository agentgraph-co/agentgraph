/**
 * ToolIntegrityPanel — surfaces #8 tool-definition pinning + drift.
 *
 * The scanner pins a canonical digest of every agent/tool definition (mcp.json,
 * server.json, SKILL.md, …) into the signed attestation. On re-scan it diffs those
 * digests: a changed/removed definition = a rug-pull after you trusted it. This panel
 * makes that signal visible — the flagship "detect when the tool changed under you".
 */
import { useState } from 'react'
import type { ToolDrift } from '../../types/scan'

interface Props {
  manifestDigest?: string | null
  digests?: Record<string, string>
  drift?: ToolDrift | null
}

function shortDigest(d?: string | null): string {
  if (!d) return '—'
  const hex = d.replace(/^sha256:/, '')
  return `${hex.slice(0, 10)}…${hex.slice(-6)}`
}

export default function ToolIntegrityPanel({ manifestDigest, digests, drift }: Props) {
  const [expanded, setExpanded] = useState(false)
  const entries = Object.entries(digests ?? {})

  // Nothing to pin — repo exposes no tool/agent definition files.
  if (!manifestDigest && entries.length === 0) return null

  const driftHit = drift?.drift_detected === true

  return (
    <div
      className={`rounded-lg border p-4 ${
        driftHit
          ? 'border-danger/50 bg-danger/5'
          : 'border-border bg-surface'
      }`}
    >
      <div className="flex items-start gap-3">
        <span className="text-lg leading-none mt-0.5" aria-hidden="true">
          {driftHit ? '⚠️' : '🔐'}
        </span>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-text-primary">
            {driftHit ? 'Tool definitions changed since last scan' : 'Tool definitions pinned'}
          </h3>
          <p className="text-xs text-text-muted mt-0.5">
            {driftHit
              ? 'A skill / MCP / tool definition was altered after it was last attested — the rug-pull signal, independent of the code scan.'
              : `${entries.length} tool definition${entries.length !== 1 ? 's' : ''} hashed and signed into this attestation. A future re-scan proves if any changes.`}
          </p>

          {/* Drift detail */}
          {driftHit && (
            <div className="mt-2 space-y-1 text-xs">
              {drift!.changed.length > 0 && (
                <p className="text-danger">
                  <span className="font-medium">Changed:</span> {drift!.changed.join(', ')}
                </p>
              )}
              {drift!.removed.length > 0 && (
                <p className="text-orange-500">
                  <span className="font-medium">Removed:</span> {drift!.removed.join(', ')}
                </p>
              )}
              {drift!.added.length > 0 && (
                <p className="text-text-muted">
                  <span className="font-medium">Added:</span> {drift!.added.join(', ')}
                </p>
              )}
              {drift!.previous_scanned_at && (
                <p className="text-text-muted">
                  Previously scanned{' '}
                  {new Date(drift!.previous_scanned_at).toLocaleDateString('en-US', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                  })}
                </p>
              )}
            </div>
          )}

          {/* Manifest digest + expandable per-file list */}
          {manifestDigest && (
            <div className="mt-2">
              <button
                onClick={() => setExpanded(!expanded)}
                className="text-xs text-primary-light hover:text-primary transition-colors cursor-pointer font-mono"
                aria-expanded={expanded}
              >
                manifest {shortDigest(manifestDigest)} {expanded ? '▲' : '▼'}
              </button>
              {expanded && entries.length > 0 && (
                <div className="mt-2 space-y-1">
                  {entries.map(([path, dg]) => (
                    <div
                      key={path}
                      className="flex items-center justify-between gap-2 rounded bg-background px-2 py-1 text-[11px]"
                    >
                      <span className="font-mono text-text-primary truncate">{path}</span>
                      <span className="font-mono text-text-muted shrink-0">{shortDigest(dg)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
