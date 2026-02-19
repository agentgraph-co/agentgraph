import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="min-h-[50vh] flex items-center justify-center">
      <div className="text-center">
        <h1 className="text-6xl font-bold text-text-muted mb-2">404</h1>
        <p className="text-lg text-text-muted mb-6">Page not found</p>
        <Link
          to="/"
          className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-md text-sm transition-colors"
        >
          Back to Home
        </Link>
      </div>
    </div>
  )
}
