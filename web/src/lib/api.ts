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

// Token refresh state — shared across concurrent requests
let isRefreshing = false
let refreshSubscribers: ((token: string) => void)[] = []

function onTokenRefreshed(token: string) {
  refreshSubscribers.forEach((cb) => cb(token))
  refreshSubscribers = []
}

function addRefreshSubscriber(cb: (token: string) => void) {
  refreshSubscribers.push(cb)
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    const url = originalRequest?.url || ''

    // Don't intercept refresh or login failures
    const isAuthEndpoint = url.includes('/auth/login') || url.includes('/auth/refresh')

    if (error.response?.status === 401 && !isAuthEndpoint && !originalRequest._retry) {
      const refreshToken = localStorage.getItem('refreshToken')

      if (refreshToken) {
        if (isRefreshing) {
          // Another refresh is in progress — queue this request
          return new Promise((resolve) => {
            addRefreshSubscriber((newToken: string) => {
              originalRequest.headers.Authorization = `Bearer ${newToken}`
              resolve(api(originalRequest))
            })
          })
        }

        originalRequest._retry = true
        isRefreshing = true

        try {
          const { data } = await axios.post(
            `${api.defaults.baseURL}/auth/refresh`,
            { refresh_token: refreshToken },
            { headers: { 'Content-Type': 'application/json' } },
          )

          localStorage.setItem('token', data.access_token)
          localStorage.setItem('refreshToken', data.refresh_token)

          originalRequest.headers.Authorization = `Bearer ${data.access_token}`
          onTokenRefreshed(data.access_token)
          isRefreshing = false

          return api(originalRequest)
        } catch {
          isRefreshing = false
          refreshSubscribers = []

          // Refresh failed — session is truly expired
          localStorage.removeItem('token')
          localStorage.removeItem('refreshToken')

          const onAuthPage = ['/login', '/register', '/forgot-password', '/reset-password'].some(
            (p) => window.location.pathname.startsWith(p),
          )
          if (!onAuthPage) {
            window.dispatchEvent(new CustomEvent('session-expired'))
            window.location.href = '/login'
          }
          return Promise.reject(error)
        }
      }

      // No refresh token — treat /auth/me 401 as session expiry
      if (url.includes('/auth/me')) {
        const hadToken = !!localStorage.getItem('token')
        localStorage.removeItem('token')
        localStorage.removeItem('refreshToken')
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
