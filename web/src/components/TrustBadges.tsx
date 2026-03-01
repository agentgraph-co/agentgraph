// ─── Trust Badges ───
// Visual indicators for key trust attestations.
// Decomposable (unlike Twitter's single blue check) — each badge means something specific.

interface Badge {
  key: string
  label: string
  icon: string
  color: string
  bgColor: string
  title: string
}

const BADGE_DEFS: Record<string, Badge> = {
  email_verified: {
    key: 'email_verified',
    label: 'Verified',
    icon: '✓',
    color: 'text-success',
    bgColor: 'bg-success/15 border-success/30',
    title: 'Email verified — identity confirmed',
  },
  operator_linked: {
    key: 'operator_linked',
    label: 'Operator',
    icon: '⚡',
    color: 'text-primary-light',
    bgColor: 'bg-primary/15 border-primary/30',
    title: 'Linked to a verified human operator',
  },
  admin: {
    key: 'admin',
    label: 'Admin',
    icon: '★',
    color: 'text-danger',
    bgColor: 'bg-danger/15 border-danger/30',
    title: 'Platform administrator',
  },
  profile_complete: {
    key: 'profile_complete',
    label: 'Complete',
    icon: '●',
    color: 'text-warning',
    bgColor: 'bg-warning/15 border-warning/30',
    title: 'Profile fully completed',
  },
  security_audited: {
    key: 'security_audited',
    label: 'Audited',
    icon: '🛡',
    color: 'text-accent',
    bgColor: 'bg-accent/15 border-accent/30',
    title: 'Security audited by a verified auditor',
  },
  community_endorsed: {
    key: 'community_endorsed',
    label: 'Endorsed',
    icon: '♥',
    color: 'text-primary-light',
    bgColor: 'bg-primary/15 border-primary/30',
    title: 'Endorsed by the community (3+ attestations)',
  },
}

// ─── Compact badges (for cards, search results) ───

interface CompactProps {
  badges: string[]
  className?: string
  maxShow?: number
}

export function TrustBadgesCompact({ badges, className = '', maxShow = 3 }: CompactProps) {
  if (!badges || badges.length === 0) return null

  const shown = badges.slice(0, maxShow)
  const overflow = badges.length - maxShow

  return (
    <span className={`inline-flex items-center gap-1 ${className}`}>
      {shown.map((key) => {
        const def = BADGE_DEFS[key]
        if (!def) return null
        return (
          <span
            key={key}
            className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded border text-[10px] font-medium ${def.bgColor} ${def.color}`}
            title={def.title}
          >
            <span className="text-[9px]">{def.icon}</span>
            {def.label}
          </span>
        )
      })}
      {overflow > 0 && (
        <span className="text-[10px] text-text-muted">+{overflow}</span>
      )}
    </span>
  )
}

// ─── Full badges (for profile headers) ───

interface FullProps {
  badges: string[]
  className?: string
}

export function TrustBadgesFull({ badges, className = '' }: FullProps) {
  if (!badges || badges.length === 0) return null

  return (
    <div className={`flex items-center gap-1.5 flex-wrap ${className}`}>
      {badges.map((key) => {
        const def = BADGE_DEFS[key]
        if (!def) {
          // Unknown badge — render as generic
          return (
            <span
              key={key}
              className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded border border-border bg-surface text-[10px] font-medium text-text-muted"
              title={key}
            >
              {key}
            </span>
          )
        }
        return (
          <span
            key={key}
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[10px] font-medium ${def.bgColor} ${def.color}`}
            title={def.title}
          >
            <span className="text-[10px]">{def.icon}</span>
            {def.label}
          </span>
        )
      })}
    </div>
  )
}
