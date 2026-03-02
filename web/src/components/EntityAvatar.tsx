// ─── EntityAvatar ───
// Avatar with entity-type-specific frame:
//   Agent → hexagonal clip-path
//   Human → circular (standard)

import { useState } from 'react'
import { getTierColor } from './trust/trustTiers'

interface EntityAvatarProps {
  name: string
  url?: string | null
  entityType?: 'human' | 'agent'
  size?: 'sm' | 'md' | 'lg'
  /** Trust tier level (0-5) — adds tier-colored ring around avatar */
  trustTier?: number
  className?: string
}

const SIZE_MAP = {
  sm: { outer: 'w-6 h-6', text: 'text-[10px]', ring: 1.5 },
  md: { outer: 'w-10 h-10', text: 'text-sm', ring: 2 },
  lg: { outer: 'w-16 h-16', text: 'text-xl', ring: 2.5 },
} as const

const HEX_CLIP = 'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)'

export default function EntityAvatar({
  name,
  url,
  entityType = 'human',
  size = 'md',
  trustTier,
  className = '',
}: EntityAvatarProps) {
  const [imgError, setImgError] = useState(false)
  const { outer, text, ring } = SIZE_MAP[size]
  const isAgent = entityType === 'agent'
  const clipStyle = isAgent ? { clipPath: HEX_CLIP } : undefined
  const borderRadius = isAgent ? undefined : '9999px'
  const initials = (name || '?').charAt(0).toUpperCase()

  const ringColor = trustTier != null ? getTierColor(trustTier) : undefined
  const ringStyle = ringColor
    ? { boxShadow: `0 0 0 ${ring}px ${ringColor}` }
    : undefined

  if (url && !imgError) {
    return (
      <img
        src={url}
        alt={name}
        loading="lazy"
        onError={() => setImgError(true)}
        className={`${outer} object-cover shrink-0 ${className}`}
        style={{
          ...clipStyle,
          borderRadius,
          ...ringStyle,
        }}
      />
    )
  }

  return (
    <div
      role="img"
      aria-label={name}
      className={`${outer} ${text} flex items-center justify-center font-bold shrink-0 ${
        isAgent ? 'bg-primary/15 text-primary-light' : 'bg-surface-hover text-text-muted'
      } ${className}`}
      style={{
        ...clipStyle,
        borderRadius,
        ...ringStyle,
      }}
    >
      {initials}
    </div>
  )
}
