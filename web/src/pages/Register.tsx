import { useState, useEffect, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export default function Register() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPass, setShowPass] = useState(false)
  const { register } = useAuth()
  const navigate = useNavigate()

  useEffect(() => { document.title = 'Create Account - AgentGraph' }, [])

  const hasUpper = /[A-Z]/.test(password)
  const hasLower = /[a-z]/.test(password)
  const hasNumber = /[0-9]/.test(password)
  const hasLength = password.length >= 8
  const passwordValid = hasUpper && hasLower && hasNumber && hasLength
  const strengthCount = [hasUpper, hasLower, hasNumber, hasLength].filter(Boolean).length

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
          <div className="relative">
            <input
              type={showPass ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              className="w-full bg-surface border border-border rounded-md px-3 py-2 pr-16 text-text focus:outline-none focus:border-primary"
            />
            <button
              type="button"
              onClick={() => setShowPass(!showPass)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-text-muted hover:text-text cursor-pointer px-1.5 py-0.5"
              tabIndex={-1}
            >
              {showPass ? 'Hide' : 'Show'}
            </button>
          </div>
          {password && (
            <div className="mt-2">
              <div className="flex gap-1 mb-1">
                {[1, 2, 3, 4].map((i) => (
                  <div
                    key={i}
                    className={`h-1 flex-1 rounded-full transition-colors ${
                      i <= strengthCount
                        ? strengthCount <= 2 ? 'bg-danger' : strengthCount === 3 ? 'bg-warning' : 'bg-success'
                        : 'bg-border'
                    }`}
                  />
                ))}
              </div>
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px]">
                <span className={hasLength ? 'text-success' : 'text-text-muted'}>8+ chars</span>
                <span className={hasUpper ? 'text-success' : 'text-text-muted'}>Uppercase</span>
                <span className={hasLower ? 'text-success' : 'text-text-muted'}>Lowercase</span>
                <span className={hasNumber ? 'text-success' : 'text-text-muted'}>Number</span>
              </div>
            </div>
          )}
        </div>
        <button
          type="submit"
          disabled={loading || !passwordValid}
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
