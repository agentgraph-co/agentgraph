import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export default function AuthCallback() {
  const { loginWithToken } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    const hash = window.location.hash.substring(1)
    const params = new URLSearchParams(hash)
    const accessToken = params.get('access_token')
    const refreshToken = params.get('refresh_token')

    if (accessToken && refreshToken) {
      loginWithToken(accessToken, refreshToken).then(() => {
        navigate('/feed', { replace: true })
      })
    } else {
      navigate('/login?error=oauth_failed', { replace: true })
    }
  }, [loginWithToken, navigate])

  return (
    <div className="flex items-center justify-center mt-20">
      <p className="text-text-muted">Signing in...</p>
    </div>
  )
}
