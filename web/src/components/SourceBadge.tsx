// ─── Source Badge ───
// Verified source badge with icon and community signals.
// Used on Profile pages and bot onboarding.

import type { ReactNode } from 'react'

interface SourceBadgeProps {
  sourceUrl: string
  sourceType: string
  communitySignals?: {
    stars?: number
    forks?: number
    downloads_monthly?: number
    likes?: number
    versions?: number
  }
  verified?: boolean
  compact?: boolean
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, '')}k`
  return String(n)
}

function extractName(url: string, sourceType: string): string {
  try {
    const u = new URL(url)
    const parts = u.pathname.split('/').filter(Boolean)
    if (sourceType === 'github' && parts.length >= 2) return `${parts[0]}/${parts[1]}`
    if (sourceType === 'npm' && parts.length >= 1) return parts.join('/')
    if (sourceType === 'pypi' && parts.length >= 2) return parts[parts.length - 1]
    if (sourceType === 'huggingface' && parts.length >= 2) return `${parts[0]}/${parts[1]}`
    if (parts.length >= 1) return parts[parts.length - 1]
    return u.hostname
  } catch {
    return url
  }
}

function GitHubIcon() {
  return (
    <svg className="w-3.5 h-3.5 shrink-0" viewBox="0 0 16 16" fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}

function NpmIcon() {
  return (
    <svg className="w-3.5 h-3.5 shrink-0" viewBox="0 0 16 16" fill="currentColor">
      <rect x="1" y="4" width="14" height="8" rx="1" fill="#CB3837" />
      <text x="8" y="10.5" textAnchor="middle" fontSize="6" fontWeight="bold" fill="white">npm</text>
    </svg>
  )
}

function PyPIIcon() {
  return (
    <svg className="w-3.5 h-3.5 shrink-0" viewBox="0 0 16 16" fill="currentColor">
      <rect x="2" y="2" width="12" height="12" rx="2" fill="#3775A9" />
      <text x="8" y="11" textAnchor="middle" fontSize="7" fontWeight="bold" fill="white">Py</text>
    </svg>
  )
}

function HuggingFaceIcon() {
  return (
    <svg className="w-3.5 h-3.5 shrink-0" viewBox="0 0 16 16" fill="currentColor">
      <circle cx="8" cy="8" r="7" fill="#FFD21E" />
      <circle cx="5.5" cy="7" r="1" fill="#1A1A1A" />
      <circle cx="10.5" cy="7" r="1" fill="#1A1A1A" />
      <path d="M5 10.5 Q8 13 11 10.5" stroke="#1A1A1A" strokeWidth="0.8" fill="none" />
    </svg>
  )
}

function LinkIcon() {
  return (
    <svg className="w-3.5 h-3.5 shrink-0" viewBox="0 0 16 16" fill="currentColor" stroke="currentColor" strokeWidth="0.5">
      <path d="M6.354 5.5H4a3 3 0 000 6h3a3 3 0 002.83-4H8.83A2 2 0 017 9.5H4a2 2 0 010-4h2.354M9.646 10.5H12a3 3 0 000-6H9a3 3 0 00-2.83 4h1.17A2 2 0 019 6.5h3a2 2 0 010 4H9.646" fill="none" strokeWidth="1.2" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg className="w-3 h-3 shrink-0 text-success" viewBox="0 0 16 16" fill="currentColor">
      <path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z" />
    </svg>
  )
}

const SOURCE_ICONS: Record<string, () => ReactNode> = {
  github: GitHubIcon,
  npm: NpmIcon,
  pypi: PyPIIcon,
  huggingface: HuggingFaceIcon,
}

export default function SourceBadge({
  sourceUrl,
  sourceType,
  communitySignals,
  verified = false,
  compact = false,
}: SourceBadgeProps) {
  const Icon = SOURCE_ICONS[sourceType.toLowerCase()] ?? LinkIcon
  const name = extractName(sourceUrl, sourceType.toLowerCase())

  const stats: { label: string; value: string }[] = []
  if (communitySignals && !compact) {
    if (communitySignals.stars != null) {
      stats.push({ label: 'stars', value: formatNumber(communitySignals.stars) })
    }
    if (communitySignals.forks != null) {
      stats.push({ label: 'forks', value: formatNumber(communitySignals.forks) })
    }
    if (communitySignals.downloads_monthly != null) {
      stats.push({ label: 'dl', value: formatNumber(communitySignals.downloads_monthly) })
    }
    if (communitySignals.likes != null) {
      stats.push({ label: 'likes', value: formatNumber(communitySignals.likes) })
    }
    if (communitySignals.versions != null) {
      stats.push({ label: 'vers', value: formatNumber(communitySignals.versions) })
    }
  }

  return (
    <a
      href={sourceUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md border border-border bg-surface hover:bg-surface-hover transition-colors text-xs text-text-muted hover:text-text cursor-pointer no-underline"
      title={verified ? `Verified source: ${sourceUrl}` : sourceUrl}
    >
      <Icon />
      <span className="truncate max-w-[160px]">{name}</span>

      {verified && <CheckIcon />}

      {stats.length > 0 && (
        <>
          <span className="text-border">|</span>
          {stats.map((s) => (
            <span key={s.label} className="whitespace-nowrap" title={s.label}>
              {s.label === 'stars' && (
                <svg className="w-3 h-3 inline-block mr-0.5 -mt-px" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M8 .25a.75.75 0 01.673.418l1.882 3.815 4.21.612a.75.75 0 01.416 1.279l-3.046 2.97.719 4.192a.75.75 0 01-1.088.791L8 12.347l-3.766 1.98a.75.75 0 01-1.088-.79l.72-4.194L.818 6.374a.75.75 0 01.416-1.28l4.21-.611L7.327.668A.75.75 0 018 .25z" />
                </svg>
              )}
              {s.label === 'forks' && (
                <svg className="w-3 h-3 inline-block mr-0.5 -mt-px" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M5 3.25a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm0 2.122a2.25 2.25 0 10-1.5 0v.878A2.25 2.25 0 005.75 8.5h1.5v2.128a2.251 2.251 0 101.5 0V8.5h1.5a2.25 2.25 0 002.25-2.25v-.878a2.25 2.25 0 10-1.5 0v.878a.75.75 0 01-.75.75h-4.5A.75.75 0 015 6.25v-.878zm3.75 7.378a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm3-8.75a.75.75 0 100-1.5.75.75 0 000 1.5z" />
                </svg>
              )}
              {s.label === 'dl' && <span className="mr-0.5">dl</span>}
              {s.label === 'likes' && <span className="mr-0.5">likes</span>}
              {s.label === 'vers' && <span className="mr-0.5">v</span>}
              {s.value}
            </span>
          ))}
        </>
      )}
    </a>
  )
}
