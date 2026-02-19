import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export default function Register() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { register } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await register(email, password, displayName)
      navigate('/feed', { state: { showVerifyBanner: true } })
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-20">
      <h1 className="text-2xl font-bold mb-6">Create your account</h1>
      {error && (
        <div className="bg-danger/10 text-danger text-sm px-4 py-2 rounded mb-4">
          {error}
        </div>
      )}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm text-text-muted mb-1">Display Name</label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            required
            minLength={2}
            maxLength={50}
            className="w-full bg-surface border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary"
          />
        </div>
        <div>
          <label className="block text-sm text-text-muted mb-1">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-full bg-surface border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary"
          />
        </div>
        <div>
          <label className="block text-sm text-text-muted mb-1">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            className="w-full bg-surface border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary"
          />
          <p className="text-xs text-text-muted mt-1">
            Must be at least 8 characters with uppercase, lowercase, and a number
          </p>
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-primary hover:bg-primary-dark text-white py-2 rounded-md transition-colors disabled:opacity-50 cursor-pointer"
        >
          {loading ? 'Creating account...' : 'Create account'}
        </button>
      </form>
      <p className="text-sm text-text-muted mt-4 text-center">
        Already have an account?{' '}
        <Link to="/login" className="text-primary-light hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  )
}
