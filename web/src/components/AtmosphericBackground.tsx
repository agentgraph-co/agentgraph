import { useSyncExternalStore } from 'react'
import { useLocation } from 'react-router-dom'
import { useTheme } from '../hooks/useTheme'

// ─── Types ───

type Intensity = 'none' | 'subtle' | 'medium' | 'full'

// ─── Reduced Motion Hook ───

function getReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function subscribe(cb: () => void) {
  const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
  mq.addEventListener('change', cb)
  return () => mq.removeEventListener('change', cb)
}

function useReducedMotion() {
  return useSyncExternalStore(subscribe, getReducedMotion, () => false)
}

// ─── Route → Intensity Mapping ───

const exactRoutes: Record<string, Intensity> = {
  '/': 'none',            // Home.tsx handles its own
  '/login': 'none',
  '/register': 'none',
  '/verify-email': 'none',
  '/forgot-password': 'none',
  '/reset-password': 'none',
  '/dashboard': 'full',
  '/feed': 'medium',
  '/search': 'medium',
  '/graph': 'medium',
  '/discover': 'medium',
  '/communities': 'medium',
  '/marketplace': 'medium',
  '/leaderboard': 'medium',
  '/notifications': 'medium',
  '/messages': 'medium',
  '/settings': 'subtle',
  '/agents': 'subtle',
  '/webhooks': 'subtle',
  '/bookmarks': 'subtle',
  '/transactions': 'subtle',
  '/marketplace/create': 'subtle',
  '/my-listings': 'subtle',
  '/tools': 'subtle',
  '/admin': 'none',
}

const prefixRoutes: Array<[string, Intensity]> = [
  ['/profile/', 'medium'],
  ['/post/', 'medium'],
  ['/m/', 'medium'],
  ['/trust/', 'medium'],
  ['/evolution/', 'medium'],
  ['/marketplace/', 'medium'],
]

function getIntensity(pathname: string): Intensity {
  const exact = exactRoutes[pathname]
  if (exact !== undefined) return exact
  for (const [prefix, intensity] of prefixRoutes) {
    if (pathname.startsWith(prefix)) return intensity
  }
  return 'none'
}

// ─── Subtle Layer (pure CSS, no JS animations) ───

function SubtleLayer() {
  const { theme } = useTheme()
  // Light mode needs stronger gradients to be visible
  const alpha = theme === 'light' ? 1 : 0.3

  return (
    <div
      className="absolute inset-0 pointer-events-none animate-gradient-breathe"
      style={{
        opacity: alpha,
        background: theme === 'light'
          ? `
            radial-gradient(ellipse at 20% 50%, rgba(13,148,136,0.08) 0%, transparent 50%),
            radial-gradient(ellipse at 80% 30%, rgba(162,28,175,0.06) 0%, transparent 50%),
            radial-gradient(ellipse at 50% 80%, rgba(217,119,6,0.05) 0%, transparent 50%)
          `
          : `
            radial-gradient(ellipse at 20% 50%, rgba(13,148,136,0.12) 0%, transparent 50%),
            radial-gradient(ellipse at 80% 30%, rgba(232,121,249,0.08) 0%, transparent 50%),
            radial-gradient(ellipse at 50% 80%, rgba(245,158,11,0.06) 0%, transparent 50%)
          `,
      }}
    />
  )
}

// ─── Main Component ───
// All non-home pages use lightweight SubtleLayer only (pure CSS gradients).
// Heavy effects (particles, glow orbs, parallax) are restricted to Home hero.

export function AtmosphericBackground({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const reducedMotion = useReducedMotion()
  const intensity = getIntensity(location.pathname)

  if (intensity === 'none' || reducedMotion) {
    return <>{children}</>
  }

  return (
    <div className="relative flex-1 flex flex-col">
      <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden" style={{ top: '3.5rem' }}>
        <SubtleLayer />
      </div>
      <div className="relative z-10 flex-1 flex flex-col">
        {children}
      </div>
    </div>
  )
}

export { getIntensity }
export type { Intensity }
