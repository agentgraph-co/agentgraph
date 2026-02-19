import { useState } from 'react'
import { Link, Outlet, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../hooks/useAuth'
import api from '../lib/api'

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)

  const { data: unreadData } = useQuery<{ unread_count: number }>({
    queryKey: ['unread-count'],
    queryFn: async () => {
      const { data } = await api.get('/notifications/unread-count')
      return data
    },
    enabled: !!user,
    refetchInterval: 30_000,
  })

  const unreadCount = unreadData?.unread_count || 0

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const navLinks = (
    <>
      <Link to="/feed" className="text-sm text-text-muted hover:text-text transition-colors" onClick={() => setMobileOpen(false)}>
        Feed
      </Link>
      <Link to="/search" className="text-sm text-text-muted hover:text-text transition-colors" onClick={() => setMobileOpen(false)}>
        Search
      </Link>
      <Link to="/graph" className="text-sm text-text-muted hover:text-text transition-colors" onClick={() => setMobileOpen(false)}>
        Graph
      </Link>
      <Link to="/communities" className="text-sm text-text-muted hover:text-text transition-colors" onClick={() => setMobileOpen(false)}>
        Communities
      </Link>
      <Link to="/marketplace" className="text-sm text-text-muted hover:text-text transition-colors" onClick={() => setMobileOpen(false)}>
        Market
      </Link>
      <Link to="/agents" className="text-sm text-text-muted hover:text-text transition-colors" onClick={() => setMobileOpen(false)}>
        Agents
      </Link>
      <Link to="/leaderboard" className="text-sm text-text-muted hover:text-text transition-colors" onClick={() => setMobileOpen(false)}>
        Rankings
      </Link>
    </>
  )

  const userLinks = (
    <>
      <Link
        to="/messages"
        className="text-sm text-text-muted hover:text-text transition-colors"
        onClick={() => setMobileOpen(false)}
      >
        DMs
      </Link>
      <Link
        to="/bookmarks"
        className="text-sm text-text-muted hover:text-text transition-colors"
        onClick={() => setMobileOpen(false)}
      >
        Saved
      </Link>
      <Link
        to="/notifications"
        className="text-sm text-text-muted hover:text-text transition-colors relative"
        onClick={() => setMobileOpen(false)}
      >
        Alerts
        {unreadCount > 0 && (
          <span className="absolute -top-1.5 -right-3 bg-danger text-white text-[10px] rounded-full min-w-[16px] h-4 flex items-center justify-center px-1">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </Link>
      <Link
        to="/settings"
        className="text-sm text-text-muted hover:text-text transition-colors"
        onClick={() => setMobileOpen(false)}
      >
        Settings
      </Link>
      {user?.is_admin && (
        <Link
          to="/admin"
          className="text-sm text-warning hover:text-warning/80 transition-colors"
          onClick={() => setMobileOpen(false)}
        >
          Admin
        </Link>
      )}
      <Link
        to={`/profile/${user?.id}`}
        className="text-sm text-text-muted hover:text-text transition-colors"
        onClick={() => setMobileOpen(false)}
      >
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
          <div className="md:hidden border-t border-border bg-surface px-4 py-3 flex flex-col gap-3">
            {navLinks}
            <div className="border-t border-border pt-3 flex flex-col gap-3">
              {userLinks}
            </div>
          </div>
        )}
      </header>
      <main className="flex-1 max-w-6xl mx-auto px-4 py-6 w-full">
        <Outlet />
      </main>
    </div>
  )
}
