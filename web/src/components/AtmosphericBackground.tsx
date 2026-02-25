import { useRef, useSyncExternalStore } from 'react'
import { useLocation } from 'react-router-dom'
import { motion, useScroll, useTransform } from 'framer-motion'
import { GradientBreath, BioluminescentGlow } from './Motion'
import { useTheme } from '../hooks/useTheme'
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

// ─── Parallax Hero Face ───
// Shows on medium + full intensity pages in both themes.
// Parallax: moves slower than scroll giving depth.
// Over content areas it's very subtle; more visible at page top.

function ParallaxHeroFace({ intensity }: { intensity: Intensity }) {
  const { theme } = useTheme()
  const ref = useRef<HTMLDivElement>(null)
  const { scrollY } = useScroll()

  // Parallax: face moves at 30% of scroll speed
  const y = useTransform(scrollY, [0, 1000], [0, -300])
  // Fade out as user scrolls into content
  const scrollOpacity = useTransform(scrollY, [0, 400], [1, 0.3])

  // Base opacity varies by intensity and theme
  const baseOpacity = theme === 'light'
    ? (intensity === 'full' ? 0.18 : 0.12)
    : (intensity === 'full' ? 0.18 : 0.10)

  return (
    <motion.div
      ref={ref}
      className="absolute inset-0 flex items-center justify-center pointer-events-none overflow-hidden"
      style={{ y, opacity: scrollOpacity }}
    >
      <img
        src={heroArt}
        alt=""
        aria-hidden="true"
        className="w-full h-full object-cover"
        style={{
          opacity: baseOpacity,
          mixBlendMode: theme === 'light' ? 'multiply' : 'lighten',
          filter: theme === 'light' ? 'contrast(1.2) brightness(0.9)' : 'none',
        }}
      />
      {/* Vignette — fades edges into the background color */}
      <div
        className="absolute inset-0"
        style={{
          background: 'radial-gradient(ellipse at center, transparent 20%, var(--color-background) 70%)',
        }}
      />
    </motion.div>
  )
}

// ─── Subtle Layer (pure CSS, no framer-motion) ───

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

// ─── Medium Layer ───

function MediumLayer() {
  return (
    <>
      <GradientBreath className="opacity-50" />
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <BioluminescentGlow size={450} className="top-[-10%] right-[-10%]" delay={0} />
      </div>
      <ParallaxHeroFace intensity="medium" />
    </>
  )
}

// ─── Full Layer (Dashboard) ───

function FullLayer() {
  return (
    <>
      <GradientBreath />
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <BioluminescentGlow size={550} className="top-[-15%] left-[-10%]" delay={0} />
        <BioluminescentGlow size={450} className="bottom-[-5%] left-[30%]" delay={6} />
      </div>
      <ParallaxHeroFace intensity="full" />
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
    <div className="relative flex-1 flex flex-col">
      {/* Background layers — full viewport width, pinned behind content */}
      <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden" style={{ top: '3.5rem' }}>
        {intensity === 'subtle' && <SubtleLayer />}
        {intensity === 'medium' && <MediumLayer />}
        {intensity === 'full' && <FullLayer />}
      </div>
      <div className="relative z-10 flex-1 flex flex-col">
        {children}
      </div>
    </div>
  )
}

export { getIntensity }
export type { Intensity }
