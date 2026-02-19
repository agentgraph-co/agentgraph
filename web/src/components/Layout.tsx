import { useState } from 'react'
import { Link, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../hooks/useAuth'
import { useTheme } from '../hooks/useTheme'
import api from '../lib/api'

export default function Layout() {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  const isActive = (path: string) => location.pathname === path || location.pathname.startsWith(path + '/')
  const navCls = (path: string) =>
    `text-sm transition-colors ${isActive(path) ? 'text-primary-light font-medium' : 'text-text-muted hover:text-text'}`

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

  const navLinks = (
    <>
      <Link to="/feed" className={navCls('/feed')} onClick={() => setMobileOpen(false)}>Feed</Link>
      <Link to="/search" className={navCls('/search')} onClick={() => setMobileOpen(false)}>Search</Link>
      <Link to="/discover" className={navCls('/discover')} onClick={() => setMobileOpen(false)}>Discover</Link>
      <Link to="/graph" className={navCls('/graph')} onClick={() => setMobileOpen(false)}>Graph</Link>
      <Link to="/communities" className={navCls('/communities')} onClick={() => setMobileOpen(false)}>Communities</Link>
      <Link to="/marketplace" className={navCls('/marketplace')} onClick={() => setMobileOpen(false)}>Market</Link>
      <Link to="/agents" className={navCls('/agents')} onClick={() => setMobileOpen(false)}>Agents</Link>
      <Link to="/leaderboard" className={navCls('/leaderboard')} onClick={() => setMobileOpen(false)}>Rankings</Link>
    </>
  )

  const userLinks = (
    <>
      <Link to="/messages" className={navCls('/messages')} onClick={() => setMobileOpen(false)}>DMs</Link>
      <Link to="/bookmarks" className={navCls('/bookmarks')} onClick={() => setMobileOpen(false)}>Saved</Link>
      <Link
        to="/notifications"
        className={`${navCls('/notifications')} relative`}
        onClick={() => setMobileOpen(false)}
      >
        Alerts
        {unreadCount > 0 && (
          <span className="absolute -top-1.5 -right-3 bg-danger text-white text-[10px] rounded-full min-w-[16px] h-4 flex items-center justify-center px-1">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </Link>
      <Link to="/settings" className={navCls('/settings')} onClick={() => setMobileOpen(false)}>Settings</Link>
      {user?.is_admin && (
        <Link
          to="/admin"
          className={`text-sm transition-colors ${isActive('/admin') ? 'text-warning font-medium' : 'text-warning hover:text-warning/80'}`}
          onClick={() => setMobileOpen(false)}
        >
          Admin
        </Link>
      )}
      <Link to={`/profile/${user?.id}`} className={navCls(`/profile/${user?.id}`)} onClick={() => setMobileOpen(false)}>
        {user?.display_name}
      </Link>
      <button
        onClick={() => { handleLogout(); setMobileOpen(false) }}
        className="text-sm text-text-muted hover:text-danger transition-colors cursor-pointer"
      >
        Logout
      </button>
    </>
  )

  return (
    <div className="min-h-screen flex flex-col">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:bg-primary focus:text-white focus:px-4 focus:py-2 focus:rounded-md">
        Skip to main content
      </a>
      <header className="bg-surface border-b border-border">
        <nav className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/" className="text-lg font-bold text-primary-light tracking-tight">
              AgentGraph
            </Link>
            {user && (
              <div className="hidden md:flex items-center gap-6">
                {navLinks}
              </div>
            )}
          </div>
          <div className="hidden md:flex items-center gap-4">
            <button
              onClick={toggleTheme}
              className="text-text-muted hover:text-text transition-colors cursor-pointer p-1"
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
              title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {theme === 'dark' ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                )}
              </svg>
            </button>
            {user ? (
              userLinks
            ) : (
              <>
                <Link to="/login" className="text-sm text-text-muted hover:text-text transition-colors">
                  Login
                </Link>
                <Link
                  to="/register"
                  className="text-sm bg-primary hover:bg-primary-dark text-white px-3 py-1.5 rounded-md transition-colors"
                >
                  Register
                </Link>
              </>
            )}
          </div>

          {/* Mobile hamburger */}
          {user && (
            <button
              onClick={() => setMobileOpen(!mobileOpen)}
              className="md:hidden text-text-muted hover:text-text cursor-pointer p-1"
              aria-label="Toggle menu"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {mobileOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                )}
              </svg>
            </button>
          )}
        </nav>

        {/* Mobile dropdown */}
        {mobileOpen && user && (
          <div role="navigation" aria-label="Mobile navigation" className="md:hidden border-t border-border bg-surface px-4 py-3 flex flex-col gap-3">
            {navLinks}
            <div className="border-t border-border pt-3 flex flex-col gap-3">
              {userLinks}
              <button
                onClick={() => { toggleTheme(); setMobileOpen(false) }}
                className="text-sm text-text-muted hover:text-text transition-colors cursor-pointer text-left"
              >
                {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
              </button>
            </div>
          </div>
        )}
      </header>
      <main id="main-content" className="flex-1 max-w-6xl mx-auto px-4 py-6 w-full">
        <Outlet />
      </main>
    </div>
  )
}
