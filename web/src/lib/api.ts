import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Only treat /auth/me 401 as session expiry — other endpoints may
      // return 401 for permission reasons without meaning the token is bad.
      const url = error.config?.url || ''
      const isAuthCheck = url.includes('/auth/me')
      if (isAuthCheck) {
        const hadToken = !!localStorage.getItem('token')
        localStorage.removeItem('token')
        const onAuthPage = ['/login', '/register', '/forgot-password', '/reset-password'].some(
          (p) => window.location.pathname.startsWith(p),
        )
        if (hadToken && !onAuthPage) {
          window.dispatchEvent(new CustomEvent('session-expired'))
          window.location.href = '/login'
        }
      }
    }
    return Promise.reject(error)
  },
)

export default api
