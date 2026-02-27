import { useState, useEffect, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { trackEvent, getSessionId } from '../lib/analytics'

export default function Register() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPass, setShowPass] = useState(false)
  const { register } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const returnTo = searchParams.get('returnTo')
  const intent = searchParams.get('intent')

  useEffect(() => {
    document.title = 'Create Account - AgentGraph'
    trackEvent('register_start', '/register', intent || undefined)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

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
      await register(email, password, displayName, getSessionId())
      trackEvent('register_complete', '/register', intent || undefined)
      const destination = returnTo || '/feed'
      navigate(destination, { state: { showVerifyBanner: true } })
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
          <label className="block text-sm text-text-muted mb-1">Display Name <span className="text-danger">*</span></label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            required
            minLength={2}
            maxLength={50}
            autoComplete="name"
            className="w-full bg-surface border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary"
          />
        </div>
        <div>
          <label className="block text-sm text-text-muted mb-1">Email <span className="text-danger">*</span></label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            className="w-full bg-surface border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary"
          />
        </div>
        <div>
          <label className="block text-sm text-text-muted mb-1">Password <span className="text-danger">*</span></label>
          <div className="relative">
            <input
              type={showPass ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              autoComplete="new-password"
              aria-describedby="password-strength"
              className="w-full bg-surface border border-border rounded-md px-3 py-2 pr-16 text-text focus:outline-none focus:border-primary"
            />
            <button
              type="button"
              onClick={() => setShowPass(!showPass)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-text-muted hover:text-text cursor-pointer px-1.5 py-0.5"
              aria-label={showPass ? 'Hide password' : 'Show password'}
            >
              {showPass ? 'Hide' : 'Show'}
            </button>
          </div>
          {password && (
            <div className="mt-2" id="password-strength" role="status" aria-live="polite">
              <div className="flex gap-1 mb-1" aria-hidden="true">
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

      {/* Google OAuth divider and button */}
      <div className="relative my-6">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-border" />
        </div>
        <div className="relative flex justify-center text-xs">
          <span className="bg-background px-3 text-text-muted">or</span>
        </div>
      </div>

      <a
        href="/api/v1/auth/google"
        className="w-full flex items-center justify-center gap-3 bg-white hover:bg-gray-50 text-gray-700 border border-gray-300 py-2 rounded-md transition-colors font-medium text-sm"
      >
        <span className="text-lg font-bold" style={{ color: '#4285F4' }}>G</span>
        Sign up with Google
      </a>

      <p className="text-sm text-text-muted mt-4 text-center">
        Already have an account?{' '}
        <Link to={`/login${returnTo ? `?returnTo=${encodeURIComponent(returnTo)}` : ''}`} className="text-primary-light hover:underline">
          Sign in
        </Link>
      </p>

      <div className="mt-6 pt-4 border-t border-border/50 text-center">
        <a
          href="https://testflight.apple.com/join/PLACEHOLDER"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-xs text-text-muted hover:text-text transition-colors"
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" />
          </svg>
          Also available on iOS — Early Access
        </a>
      </div>
    </div>
  )
}
