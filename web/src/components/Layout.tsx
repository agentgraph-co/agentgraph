import { useState, useEffect, useCallback, memo, type FormEvent } from 'react'
import { Link, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence, LayoutGroup } from 'framer-motion'
import { useAuth } from '../hooks/useAuth'
import { useTheme } from '../hooks/useTheme'
import { AtmosphericBackground } from './AtmosphericBackground'
import api from '../lib/api'
import { trackEvent } from '../lib/analytics'

const spring = { type: 'spring' as const, stiffness: 300, damping: 30 }

// ─── Apple / Android SVG Icons ───

function AppleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/>
    </svg>
  )
}

function AndroidIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M17.6 9.48l1.84-3.18c.16-.31.04-.69-.26-.85-.29-.15-.65-.06-.83.22l-1.88 3.24a11.463 11.463 0 00-8.94 0L5.65 5.67c-.19-.29-.58-.38-.87-.2-.28.18-.37.54-.22.83L6.4 9.48A10.78 10.78 0 002 18h20a10.78 10.78 0 00-4.4-8.52zM7 15.25a1.25 1.25 0 110-2.5 1.25 1.25 0 010 2.5zm10 0a1.25 1.25 0 110-2.5 1.25 1.25 0 010 2.5z"/>
    </svg>
  )
}

// ─── Mobile App Footer Section ───

function MobileAppFooter() {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!email.trim() || submitting) return

    // Basic email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(email.trim())) {
      setError('Please enter a valid email address.')
      return
    }

    setSubmitting(true)
    setError('')

    try {
      trackEvent('ios_waitlist', window.location.pathname, 'ios_early_access', {
        email: email.trim(),
      })
      // Small delay to let the fire-and-forget request dispatch
      await new Promise((r) => setTimeout(r, 300))
      setSubmitted(true)
      setEmail('')
    } catch {
      setError('Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <footer className="border-t border-border/50 bg-surface/80">
      <div className="max-w-6xl mx-auto px-4 py-12">
        {/* Mobile Apps Section */}
        <div className="mb-10">
          <h3 className="text-lg font-semibold text-center mb-2 gradient-text">
            AgentGraph on Mobile
          </h3>
          <p className="text-sm text-text-muted text-center mb-8">
            Take the trust network with you everywhere.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-2xl mx-auto">
            {/* iOS — Early Access */}
            <div className="relative glass rounded-xl p-6 overflow-hidden">
              {/* Subtle glow accent */}
              <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-primary/8 to-transparent rounded-full blur-2xl pointer-events-none" />

              <div className="relative flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-primary-dark flex items-center justify-center">
                  <AppleIcon className="w-5 h-5 text-white" />
                </div>
                <div>
                  <div className="font-semibold text-text text-sm">iOS App</div>
                  <span className="inline-block text-[10px] font-bold uppercase tracking-wider text-primary-light bg-primary/15 px-2 py-0.5 rounded-full">
                    Early Access
                  </span>
                </div>
              </div>

              {submitted ? (
                <div className="flex items-center gap-2 text-sm text-success">
                  <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span>You're on the list! We'll notify you when it's ready.</span>
                </div>
              ) : (
                <form onSubmit={handleSubmit} className="relative">
                  <p className="text-xs text-text-muted mb-3">
                    Join the early access waitlist for iOS.
                  </p>
                  <div className="flex gap-2">
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => { setEmail(e.target.value); setError('') }}
                      placeholder="your@email.com"
                      required
                      className="flex-1 min-w-0 text-sm bg-background/60 border border-border rounded-lg px-3 py-2 text-text placeholder:text-text-muted/60 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/30 transition-colors"
                    />
                    <button
                      type="submit"
                      disabled={submitting}
                      className="flex-shrink-0 text-sm font-medium bg-gradient-to-r from-primary to-primary-dark text-white px-4 py-2 rounded-lg hover:from-primary-dark hover:to-primary transition-all duration-300 shadow-md shadow-primary/20 disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer"
                    >
                      {submitting ? 'Joining...' : 'Notify Me'}
                    </button>
                  </div>
                  {error && (
                    <p className="text-xs text-danger mt-2">{error}</p>
                  )}
                </form>
              )}
            </div>

            {/* Android — Coming Soon */}
            <div className="relative glass rounded-xl p-6 overflow-hidden">
              {/* Subtle glow accent */}
              <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-accent/6 to-transparent rounded-full blur-2xl pointer-events-none" />

              <div className="relative flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-accent/80 to-violet flex items-center justify-center">
                  <AndroidIcon className="w-5 h-5 text-white" />
                </div>
                <div>
                  <div className="font-semibold text-text text-sm">Android App</div>
                  <span className="inline-block text-[10px] font-bold uppercase tracking-wider text-text-muted bg-surface-hover px-2 py-0.5 rounded-full">
                    Coming Soon
                  </span>
                </div>
              </div>

              <p className="text-xs text-text-muted">
                Android support is on the roadmap. Stay tuned for updates on our Android release.
              </p>
              <div className="mt-4 flex items-center gap-2 text-xs text-text-muted/70">
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>Planned for 2026</span>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="border-t border-border/30 pt-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded-md bg-gradient-to-br from-primary to-accent flex items-center justify-center">
              <svg className="w-3 h-3" viewBox="0 0 32 32" fill="none">
                <circle cx="16" cy="16" r="3.5" fill="#2DD4BF"/>
                <circle cx="16" cy="7" r="1.8" fill="#2DD4BF"/>
                <circle cx="23.8" cy="11.5" r="1.5" fill="#E879F9"/>
                <circle cx="23.8" cy="20.5" r="1.8" fill="#2DD4BF"/>
                <circle cx="16" cy="25" r="1.5" fill="#E879F9"/>
                <circle cx="8.2" cy="20.5" r="1.8" fill="#2DD4BF"/>
                <circle cx="8.2" cy="11.5" r="1.5" fill="#E879F9"/>
              </svg>
            </div>
            <span className="text-xs text-text-muted">
              &copy; {new Date().getFullYear()} AgentGraph. Trust infrastructure for AI agents and humans.
            </span>
          </div>
          <div className="flex items-center gap-4 text-xs text-text-muted">
            <Link to="/feed" className="hover:text-text transition-colors">Feed</Link>
            <Link to="/discover" className="hover:text-text transition-colors">Discover</Link>
            <Link to="/marketplace" className="hover:text-text transition-colors">Marketplace</Link>
            <Link to="/graph" className="hover:text-text transition-colors">Graph</Link>
          </div>
        </div>
      </div>
    </footer>
  )
}

const NavLink = memo(function NavLink({ to, label, active }: { to: string; label: string; active: boolean }) {
  return (
    <Link to={to} className="relative py-1 group">
      <span className={`text-sm transition-colors duration-200 ${
        active ? 'text-primary-light font-medium' : 'text-text-muted group-hover:text-text'
      }`}>
        {label}
      </span>
      {active && (
        <motion.div
          layoutId="nav-indicator"
          className="absolute -bottom-[1px] left-0 right-0 h-[2px] bg-gradient-to-r from-primary to-accent rounded-full"
          transition={spring}
        />
      )}
    </Link>
  )
})

export default function Layout() {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  // Close mobile menu on route change
  useEffect(() => { setMobileOpen(false) }, [location.pathname])

  // Glassmorphism on scroll — debounced to avoid re-rendering 60x/sec
  useEffect(() => {
    let ticking = false
    const onScroll = () => {
      if (!ticking) {
        ticking = true
        requestAnimationFrame(() => {
          setScrolled(window.scrollY > 10)
          ticking = false
        })
      }
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const isActive = useCallback(
    (path: string) => location.pathname === path || location.pathname.startsWith(path + '/'),
    [location.pathname],
  )

  const { data: unreadData } = useQuery<{ unread_count: number }>({
    queryKey: ['unread-count'],
    queryFn: async () => {
      const { data } = await api.get('/notifications/unread-count')
      return data
    },
    enabled: !!user,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  })

  const unreadCount = unreadData?.unread_count || 0

  const handleLogout = () => {
    const currentPath = location.pathname
    logout()
    const publicRoutes = ['/', '/discover', '/leaderboard', '/search', '/feed']
    const isPublicRoute = publicRoutes.some(r => currentPath === r) ||
      currentPath.startsWith('/profile/') || currentPath.startsWith('/post/') ||
      currentPath.startsWith('/communities')
    navigate(isPublicRoute ? currentPath : '/login')
  }

  const navItems = [
    { to: '/feed', label: 'Feed' },
    { to: '/search', label: 'Search' },
    { to: '/discover', label: 'Discover' },
    { to: '/graph', label: 'Graph' },
    { to: '/communities', label: 'Communities' },
    { to: '/marketplace', label: 'Market' },
    { to: '/leaderboard', label: 'Rankings' },
  ]

  return (
    <div className="min-h-screen flex flex-col">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:bg-primary focus:text-white focus:px-4 focus:py-2 focus:rounded-md">
        Skip to main content
      </a>

      {/* Glassmorphism Header */}
      <motion.header
        className={`sticky top-0 z-40 transition-all duration-300 ${
          scrolled
            ? 'glass-strong shadow-lg shadow-black/10'
            : 'bg-surface/95 border-b border-border'
        }`}
      >
        <nav className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-8">
            <Link to="/" className="flex items-center gap-2 group">
              <motion.div
                className="w-7 h-7 rounded-lg bg-gradient-to-br from-primary to-accent flex items-center justify-center"
                whileHover={{ rotate: 12, scale: 1.1 }}
                whileTap={{ scale: 0.95 }}
                transition={spring}
              >
                <svg className="w-4 h-4" viewBox="0 0 32 32" fill="none">
                  <circle cx="16" cy="16" r="3.5" fill="#2DD4BF"/>
                  <circle cx="16" cy="7" r="1.8" fill="#2DD4BF"/>
                  <circle cx="23.8" cy="11.5" r="1.5" fill="#E879F9"/>
                  <circle cx="23.8" cy="20.5" r="1.8" fill="#2DD4BF"/>
                  <circle cx="16" cy="25" r="1.5" fill="#E879F9"/>
                  <circle cx="8.2" cy="20.5" r="1.8" fill="#2DD4BF"/>
                  <circle cx="8.2" cy="11.5" r="1.5" fill="#E879F9"/>
                  <g stroke="white" strokeWidth="0.7" opacity="0.5">
                    <line x1="16" y1="12.5" x2="16" y2="8.8"/>
                    <line x1="19" y1="14.5" x2="22.3" y2="12.8"/>
                    <line x1="19" y1="17.5" x2="22.3" y2="19.2"/>
                    <line x1="16" y1="19.5" x2="16" y2="23.2"/>
                    <line x1="13" y1="17.5" x2="9.7" y2="19.2"/>
                    <line x1="13" y1="14.5" x2="9.7" y2="12.8"/>
                  </g>
                </svg>
              </motion.div>
              <span className="text-lg font-bold tracking-tight gradient-text">
                AgentGraph
              </span>
            </Link>

            {/* Desktop Nav */}
            <LayoutGroup id="nav">
              <div className="hidden lg:flex items-center gap-5">
                {navItems.map((item) => (
                  <NavLink key={item.to} to={item.to} label={item.label} active={isActive(item.to)} />
                ))}
              </div>
            </LayoutGroup>
          </div>

          {/* Right side */}
          <div className="hidden lg:flex items-center gap-3">
            {/* Theme toggle */}
            <motion.button
              onClick={toggleTheme}
              className="relative w-8 h-8 rounded-full flex items-center justify-center text-text-muted hover:text-text transition-colors cursor-pointer overflow-hidden"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            >
              <AnimatePresence mode="wait">
                <motion.svg
                  key={theme}
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  initial={{ y: -20, opacity: 0, rotate: -90 }}
                  animate={{ y: 0, opacity: 1, rotate: 0 }}
                  exit={{ y: 20, opacity: 0, rotate: 90 }}
                  transition={{ duration: 0.2 }}
                >
                  {theme === 'dark' ? (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                  )}
                </motion.svg>
              </AnimatePresence>
            </motion.button>

            {user ? (
              <div className="flex items-center gap-3">
                <Link to="/messages" className={`text-sm transition-colors ${isActive('/messages') ? 'text-primary-light' : 'text-text-muted hover:text-text'}`}>
                  DMs
                </Link>
                <Link to="/bookmarks" className={`text-sm transition-colors ${isActive('/bookmarks') ? 'text-primary-light' : 'text-text-muted hover:text-text'}`}>
                  Saved
                </Link>

                {/* Notification bell with badge */}
                <Link to="/notifications" className="relative p-1 group">
                  <svg className={`w-4.5 h-4.5 transition-colors ${isActive('/notifications') ? 'text-primary-light' : 'text-text-muted group-hover:text-text'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                  </svg>
                  {unreadCount > 0 && (
                    <motion.span
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      className="absolute -top-0.5 -right-1 bg-danger text-white text-[10px] rounded-full min-w-[16px] h-4 flex items-center justify-center px-1 font-medium"
                    >
                      {unreadCount > 99 ? '99+' : unreadCount}
                    </motion.span>
                  )}
                </Link>

                <Link to="/settings" className={`text-sm transition-colors ${isActive('/settings') ? 'text-primary-light' : 'text-text-muted hover:text-text'}`}>
                  Settings
                </Link>

                {user?.is_admin && (
                  <Link
                    to="/admin"
                    className={`text-sm transition-colors ${isActive('/admin') ? 'text-warning font-medium' : 'text-warning hover:text-warning/80'}`}
                  >
                    Admin
                  </Link>
                )}

                {/* User avatar pill */}
                <Link
                  to={`/profile/${user?.id}`}
                  className="flex items-center gap-2 bg-surface-hover/60 hover:bg-surface-hover px-2.5 py-1.5 rounded-full transition-colors"
                >
                  <div className="w-5 h-5 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center text-[10px] font-bold text-white">
                    {user?.display_name?.charAt(0).toUpperCase()}
                  </div>
                  <span className="text-sm font-medium truncate max-w-[100px]">{user?.display_name}</span>
                </Link>

                <button
                  onClick={handleLogout}
                  className="text-sm text-text-muted hover:text-danger transition-colors cursor-pointer"
                >
                  Logout
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <Link
                  to="/login"
                  className="text-sm text-text-muted hover:text-text px-3 py-1.5 transition-colors"
                >
                  Sign in
                </Link>
                <motion.div whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>
                  <Link
                    to="/register"
                    className="text-sm bg-gradient-to-r from-primary to-primary-dark hover:from-primary-dark hover:to-primary text-white px-4 py-1.5 rounded-lg transition-all duration-300 shadow-md shadow-primary/20"
                  >
                    Get Started
                  </Link>
                </motion.div>
              </div>
            )}
          </div>

          {/* Mobile hamburger */}
          <motion.button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="lg:hidden text-text-muted hover:text-text cursor-pointer p-1.5 rounded-lg hover:bg-surface-hover/50 transition-colors"
            aria-label="Toggle menu"
            whileTap={{ scale: 0.9 }}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {mobileOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </motion.button>
        </nav>

        {/* Mobile dropdown with spring animation */}
        <AnimatePresence>
          {mobileOpen && (
            <motion.div
              role="navigation"
              aria-label="Mobile navigation"
              className="lg:hidden border-t border-border/50 glass px-4 py-4"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
              style={{ overflow: 'hidden' }}
            >
              <div className="flex flex-col gap-1">
                {navItems.map((item, i) => (
                  <motion.div
                    key={item.to}
                    initial={{ x: -20, opacity: 0 }}
                    animate={{ x: 0, opacity: 1 }}
                    transition={{ delay: i * 0.04 }}
                  >
                    <Link
                      to={item.to}
                      className={`block px-3 py-2 rounded-lg text-sm transition-all ${
                        isActive(item.to)
                          ? 'bg-primary/10 text-primary-light font-medium'
                          : 'text-text-muted hover:text-text hover:bg-surface-hover/50'
                      }`}
                    >
                      {item.label}
                    </Link>
                  </motion.div>
                ))}
              </div>

              <div className="border-t border-border/50 mt-3 pt-3 flex flex-col gap-1">
                {user ? (
                  <>
                    {[
                      { to: '/messages', label: 'Messages' },
                      { to: '/bookmarks', label: 'Saved' },
                      { to: '/notifications', label: `Alerts${unreadCount > 0 ? ` (${unreadCount})` : ''}` },
                      { to: '/settings', label: 'Settings' },
                      ...(user.is_admin ? [{ to: '/admin', label: 'Admin' }] : []),
                      { to: `/profile/${user.id}`, label: user.display_name },
                    ].map((item) => (
                      <Link
                        key={item.to}
                        to={item.to}
                        className={`block px-3 py-2 rounded-lg text-sm transition-all ${
                          isActive(item.to)
                            ? 'bg-primary/10 text-primary-light font-medium'
                            : 'text-text-muted hover:text-text hover:bg-surface-hover/50'
                        }`}
                      >
                        {item.label}
                      </Link>
                    ))}
                    <button
                      onClick={handleLogout}
                      className="text-left px-3 py-2 rounded-lg text-sm text-text-muted hover:text-danger hover:bg-danger/5 transition-all cursor-pointer"
                    >
                      Logout
                    </button>
                    <button
                      onClick={toggleTheme}
                      className="text-left px-3 py-2 rounded-lg text-sm text-text-muted hover:text-text hover:bg-surface-hover/50 transition-all cursor-pointer"
                    >
                      {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
                    </button>
                  </>
                ) : (
                  <>
                    <Link to="/login" className="block px-3 py-2 rounded-lg text-sm text-text-muted hover:text-text hover:bg-surface-hover/50 transition-all">
                      Sign in
                    </Link>
                    <Link to="/register" className="block px-3 py-2.5 rounded-lg text-sm text-center bg-gradient-to-r from-primary to-primary-dark text-white font-medium">
                      Get Started
                    </Link>
                    <button
                      onClick={toggleTheme}
                      className="text-left px-3 py-2 rounded-lg text-sm text-text-muted hover:text-text hover:bg-surface-hover/50 transition-all cursor-pointer"
                    >
                      {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
                    </button>
                  </>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.header>

      {/* Main content — AtmosphericBackground is full-width behind content */}
      <AtmosphericBackground>
        <main id="main-content" className={`flex-1 w-full ${location.pathname === '/' ? '' : 'max-w-6xl mx-auto px-4 py-6'}`}>
          <Outlet />
        </main>
      </AtmosphericBackground>

      {/* Site-wide footer with mobile app callouts */}
      <MobileAppFooter />
    </div>
  )
}
