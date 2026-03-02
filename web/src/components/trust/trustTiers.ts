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

// ─── Tier Colors (accessible, color-blind safe) ───

const TIER_COLORS: readonly string[] = [
  '#6C7086', // 0 — gray/muted
  '#F59E0B', // 1 — amber
  '#0D9488', // 2 — teal/primary
  '#2DD4BF', // 3 — teal-bright/primary-light
  '#E879F9', // 4 — accent (gradient start)
  '#F59E0B', // 5 — gold (gradient start)
]

const TIER_GRADIENTS: Record<number, string> = {
  4: 'linear-gradient(135deg, #E879F9, #0D9488)',
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
  const nextIdx = level + 1
  const nextThreshold = nextIdx < THRESHOLDS.length ? THRESHOLDS[nextIdx] : null

  return {
    level,
    label: tiers[level].label,
    color: TIER_COLORS[level],
    gradient: TIER_GRADIENTS[level] ?? null,
    nextThreshold,
  }
}

export function getTierColor(level: number): string {
  return TIER_COLORS[Math.max(0, Math.min(5, level))] ?? TIER_COLORS[0]
}

export function getTierGradient(level: number): string | null {
  return TIER_GRADIENTS[level] ?? null
}

/** Tailwind-friendly class names for tier text color */
export function tierTextClass(level: number): string {
  switch (level) {
    case 0: return 'text-text-muted'
    case 1: return 'text-amber-400'
    case 2: return 'text-primary'
    case 3: return 'text-primary-light'
    default: return '' // tiers 4-5 use gradient style, not class
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
