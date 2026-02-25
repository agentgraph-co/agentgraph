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
      const hadToken = !!localStorage.getItem('token')
      localStorage.removeItem('token')
      // Only redirect if we had a token and aren't already on an auth page
      const onAuthPage = ['/login', '/register', '/forgot-password', '/reset-password'].some(
        (p) => window.location.pathname.startsWith(p),
      )
      if (hadToken && !onAuthPage) {
        window.dispatchEvent(new CustomEvent('session-expired'))
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

export default api
