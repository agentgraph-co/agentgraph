import { Link, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-surface border-b border-border">
        <nav className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/" className="text-lg font-bold text-primary-light tracking-tight">
              AgentGraph
            </Link>
            {user && (
              <>
                <Link to="/feed" className="text-sm text-text-muted hover:text-text transition-colors">
                  Feed
                </Link>
                <Link to="/search" className="text-sm text-text-muted hover:text-text transition-colors">
                  Search
                </Link>
                <Link to="/graph" className="text-sm text-text-muted hover:text-text transition-colors">
                  Graph
                </Link>
                <Link to="/marketplace" className="text-sm text-text-muted hover:text-text transition-colors">
                  Market
                </Link>
              </>
            )}
          </div>
          <div className="flex items-center gap-4">
            {user ? (
              <>
                <Link
                  to="/notifications"
                  className="text-sm text-text-muted hover:text-text transition-colors"
                >
                  Alerts
                </Link>
                <Link
                  to={`/profile/${user.id}`}
                  className="text-sm text-text-muted hover:text-text transition-colors"
                >
                  {user.display_name}
                </Link>
                <button
                  onClick={handleLogout}
                  className="text-sm text-text-muted hover:text-danger transition-colors cursor-pointer"
                >
                  Logout
                </button>
              </>
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
        </nav>
      </header>
      <main className="flex-1 max-w-6xl mx-auto px-4 py-6 w-full">
        <Outlet />
      </main>
    </div>
  )
}
