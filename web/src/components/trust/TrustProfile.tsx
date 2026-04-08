/**
 * TrustProfile — unified trust display with 3 dimensions + overall grade.
 *
 * Replaces the dual-axis attestation/community display with a clearer model:
 *   Identity (A-F)       — Is this entity who they claim to be?
 *   Code Security (A-F)  — Is their source code safe?
 *   Community Trust (A-F) — Do other verified people vouch for them?
 *   Overall (A-F)         — Weighted composite
 *
 * Each dimension shows: letter grade, score, one-line reason, color bar.
 */

import { Link } from 'react-router-dom'
import type { TrustComponents, SecuritySubScores } from './gradeSystem'
import {
  computeDimensions,
  getGradeInfo,
  getSecuritySubGrades,
  identityReason,
  communityReason,
} from './gradeSystem'

// ─── Dimension Row ───

function DimensionRow({
  label,
  score,
  reason,
  showBar = true,
}: {
  label: string
  score: number
  reason: string
  showBar?: boolean
}) {
  const info = getGradeInfo(score)
  return (
    <div className="flex items-center gap-3 py-2">
      {/* Letter grade */}
      <div
        className={`w-10 h-10 rounded-lg flex items-center justify-center font-bold text-lg ${info.bgClass}`}
        style={{ color: info.color }}
      >
        {info.grade}
      </div>

      {/* Label + reason + bar */}
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-sm font-medium text-text-primary">{label}</span>
          <span className="text-xs tabular-nums text-text-muted">{score}/100</span>
        </div>
        <p className="text-xs text-text-muted truncate mt-0.5">{reason}</p>
        {showBar && (
          <div className="mt-1 h-1 rounded-full bg-surface-2 overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${Math.max(2, score)}%`, backgroundColor: info.color }}
            />
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Security Sub-Score Card ───

function SecuritySubScoreCard({ scores }: { scores: SecuritySubScores }) {
  const subGrades = getSecuritySubGrades(scores)
  return (
    <div className="mt-2 pl-13 grid grid-cols-2 gap-x-4 gap-y-1">
      {Object.entries(subGrades).map(([name, info]) => (
        <div key={name} className="flex items-center gap-2">
          <span
            className="text-xs font-semibold w-5 text-center"
            style={{ color: info.color }}
          >
            {info.grade}
          </span>
          <span className="text-xs text-text-muted">{name}</span>
        </div>
      ))}
    </div>
  )
}

// ─── Overall Grade Hero ───

function OverallGradeHero({ score }: { score: number }) {
  const info = getGradeInfo(score)
  return (
    <div className="flex items-center gap-4 mb-4">
      <div
        className={`w-16 h-16 rounded-xl flex items-center justify-center font-black text-3xl ${info.bgClass}`}
        style={{ color: info.color }}
      >
        {info.grade}
      </div>
      <div>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold text-text-primary">{score}</span>
          <span className="text-sm text-text-muted">/ 100</span>
        </div>
        <p className="text-sm" style={{ color: info.color }}>{info.label}</p>
      </div>
    </div>
  )
}

// ─── Trend Sparkline (empty state → populates from history) ───

function TrendSparkline({
  history,
}: {
  history?: Array<{ date: string; score: number }>
}) {
  if (!history || history.length < 3) {
    return (
      <div className="flex items-center gap-2 text-xs text-text-muted py-2">
        <svg className="w-4 h-4 opacity-50" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
          <polyline points="1,12 5,8 9,10 15,4" />
        </svg>
        <span>Building trust history...</span>
      </div>
    )
  }

  // Render sparkline from history data
  const max = Math.max(...history.map(h => h.score))
  const min = Math.min(...history.map(h => h.score))
  const range = Math.max(max - min, 10)
  const width = 120
  const height = 24
  const points = history.map((h, i) => {
    const x = (i / (history.length - 1)) * width
    const y = height - ((h.score - min) / range) * height
    return `${x},${y}`
  }).join(' ')

  const latest = history[history.length - 1]
  const prev = history[history.length - 2]
  const delta = latest.score - prev.score
  const deltaColor = delta > 0 ? '#22C55E' : delta < 0 ? '#EF4444' : '#6C7086'

  return (
    <div className="flex items-center gap-3 py-2">
      <svg width={width} height={height} className="opacity-70">
        <polyline
          points={points}
          fill="none"
          stroke="#2DD4BF"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {delta !== 0 && (
        <span className="text-xs font-medium" style={{ color: deltaColor }}>
          {delta > 0 ? '+' : ''}{delta}
        </span>
      )}
    </div>
  )
}

// ─── Network Comparison ───

function NetworkComparison({ percentile }: { percentile?: number }) {
  if (percentile == null) {
    return null
  }
  return (
    <p className="text-xs text-text-muted py-1">
      Better than <span className="text-text-primary font-medium">{percentile}%</span> of entities
    </p>
  )
}

// ─── Changelog ───

function ChangeLog({
  changes,
}: {
  changes?: Array<{ date: string; delta: number; reason: string }>
}) {
  if (!changes || changes.length === 0) return null
  return (
    <div className="mt-3 pt-3 border-t border-border-subtle">
      <p className="text-xs font-medium text-text-muted mb-1">Recent changes</p>
      {changes.slice(0, 3).map((c, i) => (
        <div key={i} className="flex items-center gap-2 text-xs py-0.5">
          <span className="text-text-muted w-16">{c.date}</span>
          <span
            className="font-medium w-8 text-right"
            style={{ color: c.delta > 0 ? '#22C55E' : c.delta < 0 ? '#EF4444' : '#6C7086' }}
          >
            {c.delta > 0 ? '+' : ''}{c.delta}
          </span>
          <span className="text-text-muted truncate">{c.reason}</span>
        </div>
      ))}
    </div>
  )
}

// ─── Compact Grade Badge (for feed, search results) ──��

/** Minimum score to show a letter grade. Below this, show "New" pill.
 *  Set at 10 so email-verified users with a bio (~13) see a grade.
 *  Only truly empty accounts (score 0-9) show "New". */
const GRADE_THRESHOLD = 10

export function TrustGradeBadge({
  score,
  entityId,
  size = 'small',
}: {
  score: number  // accepts 0.0-1.0 (from API) or 0-100
  entityId?: string
  size?: 'micro' | 'small'
}) {
  // Normalize: if score looks like 0.0-1.0 range, convert to 0-100
  const score100 = score <= 1.0 && score > 0 ? Math.round(score * 100) : Math.round(score)
  // New/unranked users see a neutral pill instead of a red F
  const isNew = score100 < GRADE_THRESHOLD
  const info = isNew ? null : getGradeInfo(score100)

  const badge = isNew ? (
    <span
      className={`inline-flex items-center gap-1 font-medium ${
        size === 'micro' ? 'text-xs px-1.5 py-0.5' : 'text-sm px-2 py-0.5'
      } rounded-md bg-surface-2 text-text-muted`}
      title="New account — building trust profile"
    >
      New
    </span>
  ) : (
    <span
      className={`inline-flex items-center gap-1 font-semibold ${
        size === 'micro' ? 'text-xs px-1.5 py-0.5' : 'text-sm px-2 py-0.5'
      } rounded-md ${info!.bgClass}`}
      style={{ color: info!.color }}
      title={`Trust: ${info!.grade} (${score100}/100) — ${info!.label}`}
    >
      {info!.grade}
      {size !== 'micro' && <span className="text-xs opacity-70">{score100}</span>}
    </span>
  )
  if (entityId) {
    return <Link to={`/trust/${entityId}`}>{badge}</Link>
  }
  return badge
}

// ─── Main TrustProfile Component ───

interface TrustProfileProps {
  components?: TrustComponents | null
  overallScore?: number | null
  entityId?: string
  /** Security scanner sub-scores (for agents) */
  securitySubScores?: SecuritySubScores | null
  /** Score history for trend sparkline */
  scoreHistory?: Array<{ date: string; score: number }>
  /** Network percentile */
  percentile?: number
  /** Recent score changes */
  changes?: Array<{ date: string; delta: number; reason: string }>
  /** Whether this entity has been security-scanned */
  hasSecurityScan?: boolean
  /** Compact mode for sidebar */
  compact?: boolean
  /** Hide the overall grade hero (e.g. when TrustDetail page renders its own) */
  hideHero?: boolean
}

export default function TrustProfile({
  components,
  overallScore,
  entityId,
  // entityType reserved for future agent vs human display differences
  securitySubScores,
  scoreHistory,
  percentile,
  changes,
  hasSecurityScan = false,
  compact = false,
  hideHero = false,
}: TrustProfileProps) {
  const dims = computeDimensions(components, overallScore)
  const isNew = dims.overall < GRADE_THRESHOLD

  // Onboarding checklist items
  const checklistItems = components ? [
    { done: true, label: 'Account created' },
    { done: (components.verification ?? 0) >= 0.3, label: 'Email verified' },
    { done: (components.verification ?? 0) >= 0.5, label: 'Bio added' },
    { done: (components.external_reputation ?? 0) > 0, label: 'Link an external account' },
    { done: (components.community ?? 0) > 0, label: 'Get your first attestation' },
    { done: (components.activity ?? 0) > 0, label: 'Make your first post' },
    { done: (components.age ?? 0) >= 0.08, label: 'Be active for 30 days' },
  ] : []
  const checklistDone = checklistItems.filter(i => i.done).length
  const checklistTotal = checklistItems.length

  const securityReason = hasSecurityScan
    ? (dims.codeSecurity >= 81 ? 'Clean scan — no critical findings'
      : dims.codeSecurity >= 61 ? 'Minor findings detected'
      : dims.codeSecurity >= 41 ? 'Moderate findings — review recommended'
      : dims.codeSecurity > 0 ? 'Critical findings detected'
      : 'Scan complete — significant issues')
    : 'Not yet scanned'

  const content = (
    <div className="space-y-1">
      {/* Onboarding checklist for new users, grade hero for established (unless hideHero) */}
      {hideHero ? null : isNew && checklistItems.length > 0 ? (
        <div className="mb-3">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-text-primary">Building Your Trust Profile</h4>
            <span className="text-xs text-text-muted">{checklistDone}/{checklistTotal}</span>
          </div>
          <div className="h-1.5 rounded-full bg-surface-2 overflow-hidden mb-3">
            <div
              className="h-full rounded-full bg-accent transition-all duration-500"
              style={{ width: `${(checklistDone / checklistTotal) * 100}%` }}
            />
          </div>
          <div className="space-y-1.5">
            {checklistItems.map((item, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className={item.done ? 'text-success' : 'text-text-muted'}>
                  {item.done ? '✓' : '○'}
                </span>
                <span className={item.done ? 'text-text-muted line-through' : 'text-text-primary'}>
                  {item.label}
                </span>
              </div>
            ))}
          </div>
          <p className="text-xs text-text-muted mt-2">
            Complete {Math.max(0, 4 - checklistDone)} more to earn your first trust grade
          </p>
        </div>
      ) : (
        <OverallGradeHero score={dims.overall} />
      )}

      {/* Trend + comparison (only for established users) */}
      {!isNew && <TrendSparkline history={scoreHistory} />}
      {!isNew && <NetworkComparison percentile={percentile} />}

      {/* 3 dimensions */}
      <div className="space-y-0.5 pt-2 border-t border-border-subtle">
        <DimensionRow
          label="Identity"
          score={dims.identity}
          reason={components ? identityReason(components) : 'Unknown'}
        />

        <DimensionRow
          label="Code Security"
          score={hasSecurityScan ? dims.codeSecurity : 0}
          reason={securityReason}
          showBar={hasSecurityScan}
        />
        {securitySubScores && hasSecurityScan && !compact && (
          <SecuritySubScoreCard scores={securitySubScores} />
        )}

        <DimensionRow
          label="Community Trust"
          score={dims.communityTrust}
          reason={components ? communityReason(components) : 'Unknown'}
        />
      </div>

      {/* Changelog */}
      {!compact && <ChangeLog changes={changes} />}
    </div>
  )

  // When embedded in TrustDetail (hideHero), render dimensions only — no card wrapper
  if (hideHero) {
    return content
  }

  if (entityId) {
    return (
      <div className="rounded-xl bg-surface-1 border border-border-subtle p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-text-primary">Trust Profile</h3>
          <Link
            to={`/trust/${entityId}`}
            className="text-xs text-accent hover:underline"
          >
            Full breakdown →
          </Link>
        </div>
        {content}
      </div>
    )
  }

  return content
}
