// ─── Trust Tier Computation ───
// Rotten-Tomatoes-style tier system where the visual graphic changes at each level.
// Builds on computeDualTrust() from DualTrustScore.tsx — doesn't replace it.

export interface TrustTier {
  level: 0 | 1 | 2 | 3 | 4 | 5
  label: string
  color: string
  /** CSS gradient string for tiers 4-5, otherwise same as color */
  gradient: string | null
  nextThreshold: number | null
}

export interface PrestigeBadge {
  label: string
  description: string
}

// ─── Tier Definitions ───

const ATTESTATION_TIERS: readonly { min: number; label: string }[] = [
  { min: 0, label: 'Unverified' },
  { min: 20, label: 'Basic' },
  { min: 40, label: 'Confirmed' },
  { min: 60, label: 'Validated' },
  { min: 80, label: 'Verified' },
  { min: 90, label: 'Certified' },
]

const COMMUNITY_TIERS: readonly { min: number; label: string }[] = [
  { min: 0, label: 'Unknown' },
  { min: 20, label: 'Emerging' },
  { min: 40, label: 'Connected' },
  { min: 60, label: 'Established' },
  { min: 80, label: 'Trusted' },
  { min: 90, label: 'Pillar' },
]

// ─── Tier Colors (axis-specific, accessible, color-blind safe) ───
// Attestation = pink/fuchsia spectrum — institutional/credential trust
// Community   = warm spectrum (green/emerald) — peer/social trust

const ATTESTATION_COLORS: readonly string[] = [
  '#6C7086', // 0 — gray/muted (no credentials)
  '#F0ABFC', // 1 — fuchsia-300 (basic verification)
  '#E879F9', // 2 — fuchsia-400 / accent (confirmed)
  '#D946EF', // 3 — fuchsia-500 (validated)
  '#C026D3', // 4 — fuchsia-600 (gradient start — verified)
  '#F59E0B', // 5 — gold (certified — prestige tier)
]

const COMMUNITY_COLORS: readonly string[] = [
  '#6C7086', // 0 — gray/muted (unknown)
  '#84CC16', // 1 — lime (emerging)
  '#22C55E', // 2 — green (connected)
  '#10B981', // 3 — emerald (established)
  '#F472B6', // 4 — pink/rose (gradient start — trusted)
  '#F59E0B', // 5 — gold (pillar — prestige tier)
]

const ATTESTATION_GRADIENTS: Record<number, string> = {
  4: 'linear-gradient(135deg, #D946EF, #A21CAF)',
  5: 'linear-gradient(135deg, #F59E0B, #EAB308)',
}

const COMMUNITY_GRADIENTS: Record<number, string> = {
  4: 'linear-gradient(135deg, #F472B6, #EC4899)',
  5: 'linear-gradient(135deg, #F59E0B, #EAB308)',
}

// ─── Tier Thresholds ───

const THRESHOLDS = [0, 20, 40, 60, 80, 90] as const

function resolveTierLevel(score: number): 0 | 1 | 2 | 3 | 4 | 5 {
  if (score >= 90) return 5
  if (score >= 80) return 4
  if (score >= 60) return 3
  if (score >= 40) return 2
  if (score >= 20) return 1
  return 0
}

// ─── Public API ───

export type TrustAxis = 'attestation' | 'community'

export function computeTier(score: number, axis: TrustAxis): TrustTier {
  const level = resolveTierLevel(score)
  const tiers = axis === 'attestation' ? ATTESTATION_TIERS : COMMUNITY_TIERS
  const colors = axis === 'attestation' ? ATTESTATION_COLORS : COMMUNITY_COLORS
  const gradients = axis === 'attestation' ? ATTESTATION_GRADIENTS : COMMUNITY_GRADIENTS
  const nextIdx = level + 1
  const nextThreshold = nextIdx < THRESHOLDS.length ? THRESHOLDS[nextIdx] : null

  return {
    level,
    label: tiers[level].label,
    color: colors[level],
    gradient: gradients[level] ?? null,
    nextThreshold,
  }
}

export function getTierColor(level: number, axis: TrustAxis = 'attestation'): string {
  const colors = axis === 'attestation' ? ATTESTATION_COLORS : COMMUNITY_COLORS
  return colors[Math.max(0, Math.min(5, level))] ?? colors[0]
}

export function getTierGradient(level: number, axis: TrustAxis = 'attestation'): string | null {
  const gradients = axis === 'attestation' ? ATTESTATION_GRADIENTS : COMMUNITY_GRADIENTS
  return gradients[level] ?? null
}

/** Tailwind-friendly class names for tier text color */
export function tierTextClass(level: number, axis: TrustAxis = 'attestation'): string {
  if (level >= 4) return '' // tiers 4-5 use gradient style, not class
  if (level === 0) return 'text-text-muted'
  if (axis === 'attestation') {
    switch (level) {
      case 1: return 'text-fuchsia-300'
      case 2: return 'text-fuchsia-400'
      case 3: return 'text-fuchsia-500'
      default: return ''
    }
  }
  // community
  switch (level) {
    case 1: return 'text-lime-500'
    case 2: return 'text-green-500'
    case 3: return 'text-emerald-500'
    default: return ''
  }
}

/**
 * Prestige badge: "Mycelium Verified"
 * Requires: both axes ≥80 (tier 4+), account age ≥90 days, 3+ attestations from high-trust entities
 */
export function getPrestigeBadge(
  attestation: number,
  community: number,
  accountAgeDays: number,
  attestationCount: number,
): PrestigeBadge | null {
  if (attestation >= 80 && community >= 80 && accountAgeDays >= 90 && attestationCount >= 3) {
    return {
      label: 'Mycelium Verified',
      description: 'Both trust axes at Tier 4+, 90+ day account, 3+ high-trust attestations',
    }
  }
  return null
}

/** Progress percentage toward next tier (0-100), or null if max tier */
export function progressToNextTier(score: number): number | null {
  const level = resolveTierLevel(score)
  const nextIdx = level + 1
  if (nextIdx >= THRESHOLDS.length) return null
  const currentMin = THRESHOLDS[level]
  const nextMin = THRESHOLDS[nextIdx]
  const range = nextMin - currentMin
  return Math.round(((score - currentMin) / range) * 100)
}
