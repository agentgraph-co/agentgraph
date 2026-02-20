/**
 * Reusable animation primitives built on framer-motion.
 * Import these in any page for scroll-triggered reveals,
 * staggered lists, counters, and ambient effects.
 */
import { useEffect, useRef } from 'react'
import {
  motion,
  useInView,
  useScroll,
  useTransform,
  type Variant,
} from 'framer-motion'

// ─── Spring configs ───

export const spring = {
  gentle: { type: 'spring' as const, stiffness: 120, damping: 20 },
  snappy: { type: 'spring' as const, stiffness: 300, damping: 30 },
  bouncy: { type: 'spring' as const, stiffness: 400, damping: 25, mass: 0.8 },
}

// ─── Fade In (scroll-triggered) ───

interface FadeInProps {
  children: React.ReactNode
  className?: string
  delay?: number
  direction?: 'up' | 'down' | 'left' | 'right' | 'none'
  duration?: number
  once?: boolean
}

const directionOffset = {
  up: { y: 40 },
  down: { y: -40 },
  left: { x: 40 },
  right: { x: -40 },
  none: {},
}

export function FadeIn({
  children,
  className = '',
  delay = 0,
  direction = 'up',
  duration = 0.6,
  once = true,
}: FadeInProps) {
  const ref = useRef<HTMLDivElement>(null)
  const isInView = useInView(ref, { once, margin: '-50px' })

  return (
    <motion.div
      ref={ref}
      className={className}
      initial={{ opacity: 0, ...directionOffset[direction] }}
      animate={isInView ? { opacity: 1, x: 0, y: 0 } : undefined}
      transition={{ duration, delay, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      {children}
    </motion.div>
  )
}

// ─── Stagger Children ───

interface StaggerProps {
  children: React.ReactNode
  className?: string
  staggerDelay?: number
  once?: boolean
}

export function Stagger({
  children,
  className = '',
  staggerDelay = 0.08,
  once = true,
}: StaggerProps) {
  const ref = useRef<HTMLDivElement>(null)
  const isInView = useInView(ref, { once, margin: '-30px' })

  return (
    <motion.div
      ref={ref}
      className={className}
      initial="hidden"
      animate={isInView ? 'visible' : 'hidden'}
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: staggerDelay } },
      }}
    >
      {children}
    </motion.div>
  )
}

// Item inside a Stagger container
interface StaggerItemProps {
  children: React.ReactNode
  className?: string
}

const staggerItemVariants: Record<string, Variant> = {
  hidden: { opacity: 0, y: 20, scale: 0.97 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] },
  },
}

export function StaggerItem({ children, className = '' }: StaggerItemProps) {
  return (
    <motion.div className={className} variants={staggerItemVariants}>
      {children}
    </motion.div>
  )
}

// ─── Parallax Layer ───

interface ParallaxProps {
  children: React.ReactNode
  className?: string
  speed?: number // 0 = static, 1 = full scroll speed, negative = reverse
}

export function Parallax({ children, className = '', speed = 0.3 }: ParallaxProps) {
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ['start end', 'end start'],
  })
  const y = useTransform(scrollYProgress, [0, 1], [speed * -100, speed * 100])

  return (
    <motion.div ref={ref} className={className} style={{ y }}>
      {children}
    </motion.div>
  )
}

// ─── Animated Counter ───

interface CounterProps {
  value: number
  className?: string
  duration?: number
}

export function Counter({ value, className = '', duration = 1.5 }: CounterProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const isInView = useInView(ref, { once: true })

  return (
    <motion.span
      ref={ref}
      className={className}
      initial={{ opacity: 0 }}
      animate={isInView ? { opacity: 1 } : undefined}
    >
      {isInView ? (
        <motion.span
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
        >
          <AnimatedNumber value={value} duration={duration} />
        </motion.span>
      ) : (
        '0'
      )}
    </motion.span>
  )
}

function AnimatedNumber({ value, duration }: { value: number; duration: number }) {
  return (
    <motion.span
      initial="from"
      animate="to"
      variants={{
        from: { '--num': 0 } as Record<string, number>,
        to: { '--num': value } as Record<string, number>,
      }}
      transition={{ duration, ease: [0.25, 0.46, 0.45, 0.94] }}
      style={{ counterSet: 'num var(--num)' }}
    >
      <CounterDisplay target={value} duration={duration} />
    </motion.span>
  )
}

function CounterDisplay({ target, duration }: { target: number; duration: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  const startRef = useRef(0)
  const frameRef = useRef(0)

  useEffect(() => {
    const animate = () => {
      const elapsed = (performance.now() - startRef.current) / 1000
      const progress = Math.min(elapsed / duration, 1)
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3)
      const current = Math.round(eased * target)
      if (ref.current) {
        ref.current.textContent = current.toLocaleString()
      }
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(animate)
      }
    }

    startRef.current = performance.now()
    frameRef.current = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frameRef.current)
  }, [target, duration])

  return <span ref={ref}>0</span>
}

// ─── Floating Orb (ambient decoration) ───

interface OrbProps {
  className?: string
  color?: string
  size?: number
  delay?: number
}

export function Orb({
  className = '',
  color = 'var(--color-primary)',
  size = 300,
  delay = 0,
}: OrbProps) {
  return (
    <motion.div
      className={`absolute rounded-full pointer-events-none blur-3xl ${className}`}
      style={{
        width: size,
        height: size,
        background: `radial-gradient(circle, ${color} 0%, transparent 70%)`,
      }}
      animate={{
        x: [0, 30, -20, 10, 0],
        y: [0, -25, 15, -10, 0],
        scale: [1, 1.1, 0.95, 1.05, 1],
      }}
      transition={{
        duration: 12,
        delay,
        repeat: Infinity,
        ease: 'easeInOut',
      }}
    />
  )
}

// ─── Magnetic Hover Effect ───

interface MagneticProps {
  children: React.ReactNode
  className?: string
  strength?: number
}

export function Magnetic({ children, className = '', strength: _strength = 0.3 }: MagneticProps) {
  return (
    <motion.div
      className={className}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      transition={spring.snappy}
    >
      {children}
    </motion.div>
  )
}

// ─── Page Transition Wrapper ───

interface PageTransitionProps {
  children: React.ReactNode
  className?: string
}

export function PageTransition({ children, className = '' }: PageTransitionProps) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      {children}
    </motion.div>
  )
}

// Re-export motion for use in other components
export { motion, useInView, useScroll, useTransform }
