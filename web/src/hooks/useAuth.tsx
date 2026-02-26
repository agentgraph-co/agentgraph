import { createContext, useContext, useState, useEffect, useCallback, useMemo, type ReactNode } from 'react'
import api from '../lib/api'
import type { Entity } from '../types'

interface AuthContextType {
  user: Entity | null
  token: string | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, displayName: string, sessionId?: string) => Promise<void>
  logout: () => void
  isLoading: boolean
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Entity | null>(null)
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('token'))
  const [isLoading, setIsLoading] = useState(true)

  const fetchMe = useCallback(async () => {
    try {
      const { data } = await api.get('/auth/me')
      setUser(data)
    } catch {
      localStorage.removeItem('token')
      setToken(null)
      setUser(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (token) {
      fetchMe()
    } else {
      setIsLoading(false)
    }
  }, [token, fetchMe])

  const login = useCallback(async (email: string, password: string) => {
    const { data } = await api.post('/auth/login', { email, password })
    localStorage.setItem('token', data.access_token)
    setToken(data.access_token)
  }, [])

  const register = useCallback(async (email: string, password: string, displayName: string, sessionId?: string) => {
    await api.post('/auth/register', {
      email,
      password,
      display_name: displayName,
    }, sessionId ? { params: { session_id: sessionId } } : undefined)
    // Inline login logic to avoid stale closure over login
    const { data } = await api.post('/auth/login', { email, password })
    localStorage.setItem('token', data.access_token)
    setToken(data.access_token)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('token')
    setToken(null)
    setUser(null)
  }, [])

  const contextValue = useMemo(() => ({
    user, token, login, register, logout, isLoading,
  }), [user, token, login, register, logout, isLoading])

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
