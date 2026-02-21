import { useSyncExternalStore } from 'react'
import { useLocation } from 'react-router-dom'
import { GradientBreath, BioluminescentGlow } from './Motion'
import heroArt from '../assets/hero-art.png'

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

// ─── Subtle Layer (pure CSS, no framer-motion) ───

function SubtleLayer() {
  return (
    <div
      className="absolute inset-0 pointer-events-none animate-gradient-breathe"
      style={{
        opacity: 0.3,
        background: `
          radial-gradient(ellipse at 20% 50%, rgba(13,148,136,0.12) 0%, transparent 50%),
          radial-gradient(ellipse at 80% 30%, rgba(232,121,249,0.08) 0%, transparent 50%),
          radial-gradient(ellipse at 50% 80%, rgba(245,158,11,0.06) 0%, transparent 50%)
        `,
      }}
    />
  )
}

// ─── Medium Layer ───

function MediumLayer() {
  return (
    <>
      <GradientBreath className="opacity-50" />
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <BioluminescentGlow size={400} className="top-[-10%] right-[-5%]" delay={0} />
      </div>
    </>
  )
}

// ─── Full Layer (Dashboard) ───

function FullLayer() {
  return (
    <>
      <GradientBreath />
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <BioluminescentGlow size={500} className="top-[-15%] left-[-10%]" delay={0} />
        <BioluminescentGlow size={400} className="top-[20%] right-[-8%]" delay={4} />
        <BioluminescentGlow size={350} className="bottom-[-5%] left-[30%]" delay={8} />
      </div>
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none atmosphere-hero-art">
        <img
          src={heroArt}
          alt=""
          aria-hidden="true"
          className="w-full h-full object-cover opacity-[0.10] mix-blend-lighten"
        />
        <div
          className="absolute inset-0"
          style={{
            background: 'radial-gradient(ellipse at center, transparent 20%, var(--color-background) 70%)',
          }}
        />
      </div>
    </>
  )
}

// ─── Main Component ───

export function AtmosphericBackground({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const reducedMotion = useReducedMotion()
  const intensity = getIntensity(location.pathname)

  if (intensity === 'none' || reducedMotion) {
    return <>{children}</>
  }

  return (
    <div className="relative">
      <div className="absolute inset-0 pointer-events-none z-0 overflow-hidden">
        {intensity === 'subtle' && <SubtleLayer />}
        {intensity === 'medium' && <MediumLayer />}
        {intensity === 'full' && <FullLayer />}
      </div>
      <div className="relative z-10">
        {children}
      </div>
    </div>
  )
}

export { getIntensity }
export type { Intensity }
