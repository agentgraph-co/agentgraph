import { useState, useEffect } from 'react'
import { Link, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '../hooks/useAuth'
import { useTheme } from '../hooks/useTheme'
import api from '../lib/api'

const spring = { type: 'spring' as const, stiffness: 300, damping: 30 }

export default function Layout() {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  // Close mobile menu on route change
  useEffect(() => { setMobileOpen(false) }, [location.pathname])

  // Glassmorphism on scroll
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 10)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const isActive = (path: string) => location.pathname === path || location.pathname.startsWith(path + '/')

  const { data: unreadData } = useQuery<{ unread_count: number }>({
    queryKey: ['unread-count'],
    queryFn: async () => {
      const { data } = await api.get('/notifications/unread-count')
      return data
    },
    enabled: !!user,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  })

  const unreadCount = unreadData?.unread_count || 0

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  // Nav link with animated active indicator
  const NavLink = ({ to, label }: { to: string; label: string }) => (
    <Link to={to} className="relative py-1 group">
      <span className={`text-sm transition-colors duration-200 ${
        isActive(to) ? 'text-primary-light font-medium' : 'text-text-muted group-hover:text-text'
      }`}>
        {label}
      </span>
      {isActive(to) && (
        <motion.div
          layoutId="nav-indicator"
          className="absolute -bottom-[1px] left-0 right-0 h-[2px] bg-gradient-to-r from-primary to-accent rounded-full"
          transition={spring}
        />
      )}
    </Link>
  )

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
            : 'bg-surface/80 backdrop-blur-sm border-b border-border'
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
                <svg className="w-4 h-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M12 2L2 7l10 5 10-5-10-5z" />
                  <path d="M2 17l10 5 10-5" />
                  <path d="M2 12l10 5 10-5" />
                </svg>
              </motion.div>
              <span className="text-lg font-bold tracking-tight gradient-text">
                AgentGraph
              </span>
            </Link>

            {/* Desktop Nav */}
            <div className="hidden lg:flex items-center gap-5">
              {navItems.map((item) => (
                <NavLink key={item.to} {...item} />
              ))}
            </div>
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

      {/* Main content */}
      <main id="main-content" className="flex-1 max-w-6xl mx-auto px-4 py-6 w-full">
        <Outlet />
      </main>
    </div>
  )
}
