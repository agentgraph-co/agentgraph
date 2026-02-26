import { useRef, useSyncExternalStore } from 'react'
import { useLocation } from 'react-router-dom'
import { motion, useScroll, useTransform } from 'framer-motion'
import { GradientBreath } from './Motion'
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
  '/login': 'medium',
  '/register': 'medium',
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
    ? (intensity === 'full' ? 0.20 : 0.14)
    : (intensity === 'full' ? 0.22 : 0.12)

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
        className="w-full h-full object-cover animate-hero-breathe"
        style={{
          opacity: baseOpacity,
          mixBlendMode: theme === 'light' ? 'multiply' : 'screen',
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

// ─── Network Pulse — animated mycelium lines ───
// Pure CSS stroke-dashoffset animation. Energy flows along organic curves.
// Slower and more subtle than the Home page NetworkIllustration.

function NetworkPulse({ opacity = 0.12 }: { opacity?: number }) {
  return (
    <svg
      viewBox="0 0 1200 800"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="absolute inset-0 w-full h-full pointer-events-none"
      preserveAspectRatio="xMidYMid slice"
      style={{ opacity }}
    >
      <defs>
        <linearGradient id="bgConnTeal" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#2DD4BF" />
          <stop offset="100%" stopColor="#0D9488" />
        </linearGradient>
        <linearGradient id="bgConnFuchsia" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#E879F9" />
          <stop offset="100%" stopColor="#A21CAF" />
        </linearGradient>
        <linearGradient id="bgConnAmber" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#F59E0B" />
          <stop offset="100%" stopColor="#D97706" />
        </linearGradient>
      </defs>

      {/* Flowing connections — staggered animation delays */}
      <g strokeWidth="0.8" fill="none">
        {/* Central web */}
        <path d="M600 400 Q520 350 420 380" stroke="url(#bgConnTeal)" className="animate-network-flow" style={{ animationDelay: '0s' }} />
        <path d="M600 400 Q680 340 780 360" stroke="url(#bgConnFuchsia)" className="animate-network-flow" style={{ animationDelay: '3s' }} />
        <path d="M600 400 Q560 480 480 520" stroke="url(#bgConnAmber)" className="animate-network-flow" style={{ animationDelay: '6s' }} />
        <path d="M600 400 Q660 490 760 510" stroke="url(#bgConnTeal)" className="animate-network-flow" style={{ animationDelay: '9s' }} />
        <path d="M600 400 Q580 310 560 240" stroke="url(#bgConnFuchsia)" className="animate-network-flow" style={{ animationDelay: '2s' }} />
        <path d="M600 400 Q640 310 680 230" stroke="url(#bgConnAmber)" className="animate-network-flow" style={{ animationDelay: '5s' }} />

        {/* Left tendrils */}
        <path d="M420 380 Q350 340 280 360" stroke="url(#bgConnTeal)" className="animate-network-flow" style={{ animationDelay: '1s' }} />
        <path d="M280 360 Q220 310 160 340" stroke="url(#bgConnAmber)" className="animate-network-flow" style={{ animationDelay: '4s' }} />
        <path d="M420 380 Q380 440 340 480" stroke="url(#bgConnFuchsia)" className="animate-network-flow" style={{ animationDelay: '7s' }} />
        <path d="M160 340 Q110 290 80 250" stroke="url(#bgConnTeal)" className="animate-network-flow" style={{ animationDelay: '10s' }} />

        {/* Right tendrils */}
        <path d="M780 360 Q850 320 920 350" stroke="url(#bgConnFuchsia)" className="animate-network-flow" style={{ animationDelay: '2.5s' }} />
        <path d="M920 350 Q980 310 1040 330" stroke="url(#bgConnTeal)" className="animate-network-flow" style={{ animationDelay: '5.5s' }} />
        <path d="M780 360 Q820 420 880 450" stroke="url(#bgConnAmber)" className="animate-network-flow" style={{ animationDelay: '8s' }} />
        <path d="M1040 330 Q1090 290 1140 310" stroke="url(#bgConnAmber)" className="animate-network-flow" style={{ animationDelay: '11s' }} />

        {/* Top branches */}
        <path d="M560 240 Q500 190 440 200" stroke="url(#bgConnTeal)" className="animate-network-flow" style={{ animationDelay: '3.5s' }} />
        <path d="M680 230 Q730 180 780 190" stroke="url(#bgConnAmber)" className="animate-network-flow" style={{ animationDelay: '6.5s' }} />

        {/* Bottom branches */}
        <path d="M480 520 Q430 570 380 580" stroke="url(#bgConnTeal)" className="animate-network-flow" style={{ animationDelay: '4.5s' }} />
        <path d="M760 510 Q810 560 860 570" stroke="url(#bgConnFuchsia)" className="animate-network-flow" style={{ animationDelay: '7.5s' }} />
      </g>

      {/* Nodes — subtle pulsing dots at junctions */}
      <g>
        <circle cx="600" cy="400" r="3" fill="#2DD4BF" className="animate-pulse-glow" />
        <circle cx="420" cy="380" r="2" fill="#2DD4BF" className="animate-pulse-glow" style={{ animationDelay: '1s' }} />
        <circle cx="780" cy="360" r="2.5" fill="#E879F9" className="animate-pulse-glow" style={{ animationDelay: '2s' }} />
        <circle cx="480" cy="520" r="2" fill="#F59E0B" className="animate-pulse-glow" style={{ animationDelay: '3s' }} />
        <circle cx="760" cy="510" r="1.5" fill="#2DD4BF" className="animate-pulse-glow" style={{ animationDelay: '4s' }} />
        <circle cx="560" cy="240" r="2" fill="#E879F9" className="animate-pulse-glow" style={{ animationDelay: '5s' }} />
        <circle cx="680" cy="230" r="1.5" fill="#F59E0B" className="animate-pulse-glow" style={{ animationDelay: '6s' }} />
        <circle cx="280" cy="360" r="1.5" fill="#E879F9" className="animate-pulse-glow" style={{ animationDelay: '1.5s' }} />
        <circle cx="920" cy="350" r="2" fill="#F59E0B" className="animate-pulse-glow" style={{ animationDelay: '3.5s' }} />
        <circle cx="160" cy="340" r="1.5" fill="#2DD4BF" className="animate-pulse-glow" style={{ animationDelay: '5.5s' }} />
        <circle cx="1040" cy="330" r="1.5" fill="#E879F9" className="animate-pulse-glow" style={{ animationDelay: '7.5s' }} />
      </g>
    </svg>
  )
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

// ─── Medium Layer ───
// GradientBreath + parallax face. No BioluminescentGlow (GPU-heavy).

function MediumLayer() {
  return (
    <>
      <GradientBreath className="opacity-50" />
      <ParallaxHeroFace intensity="medium" />
      <NetworkPulse opacity={0.08} />
    </>
  )
}

// ─── Full Layer (Dashboard) ───
// Richer gradients + parallax face + network pulse. No BioluminescentGlow (GPU-heavy).

function FullLayer() {
  return (
    <>
      <GradientBreath />
      <ParallaxHeroFace intensity="full" />
      <NetworkPulse opacity={0.14} />
    </>
  )
}

// ─── Auth routes get full-bleed background (no header offset) ───

const authRoutes = new Set(['/login', '/register', '/forgot-password', '/reset-password'])

// ─── Main Component ───

export function AtmosphericBackground({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const reducedMotion = useReducedMotion()
  const intensity = getIntensity(location.pathname)

  if (intensity === 'none' || reducedMotion) {
    return <>{children}</>
  }

  const isAuth = authRoutes.has(location.pathname)

  return (
    <div className="relative flex-1 flex flex-col">
      {/* Background layers — full viewport width, pinned behind content */}
      <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden" style={{ top: isAuth ? 0 : '3.5rem' }}>
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
