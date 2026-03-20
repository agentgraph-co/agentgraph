import api from './api'

const SESSION_KEY = 'ag_session_id'
const UTM_KEY = 'ag_utm'

export function getSessionId(): string {
  let id = localStorage.getItem(SESSION_KEY)
  if (!id) {
    id = typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2) + Date.now().toString(36)
    localStorage.setItem(SESSION_KEY, id)
  }
  return id
}

/**
 * Capture UTM params from the current URL and store in sessionStorage.
 * Should be called once on app mount. Overwrites only if UTM params are present.
 */
export function captureUtmParams(): void {
  try {
    const params = new URLSearchParams(window.location.search)
    const utm_source = params.get('utm_source')
    const utm_medium = params.get('utm_medium')
    const utm_campaign = params.get('utm_campaign')
    if (utm_source || utm_medium || utm_campaign) {
      const utm: Record<string, string> = {}
      if (utm_source) utm.utm_source = utm_source
      if (utm_medium) utm.utm_medium = utm_medium
      if (utm_campaign) utm.utm_campaign = utm_campaign
      sessionStorage.setItem(UTM_KEY, JSON.stringify(utm))
    }
  } catch {
    // Silently ignore — sessionStorage may be unavailable
  }
}

/**
 * Retrieve stored UTM params from sessionStorage.
 * Returns empty object if none captured.
 */
export function getUtmParams(): Record<string, string> {
  try {
    const raw = sessionStorage.getItem(UTM_KEY)
    if (raw) return JSON.parse(raw) as Record<string, string>
  } catch {
    // Silently ignore
  }
  return {}
}

export function trackEvent(
  type: string,
  page: string,
  intent?: string,
  metadata?: Record<string, unknown>,
): void {
  const utm = getUtmParams()
  const mergedMetadata = { ...utm, ...metadata }

  const body: Record<string, unknown> = {
    event_type: type,
    session_id: getSessionId(),
    page,
  }
  if (intent) body.intent = intent
  if (Object.keys(mergedMetadata).length > 0) body.metadata = mergedMetadata

  // Fire and forget — don't block UI
  api.post('/analytics/event', body).catch(() => {
    // Silently ignore analytics failures
  })
}
