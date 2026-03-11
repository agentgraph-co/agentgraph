import api from './api'

const SESSION_KEY = 'ag_session_id'

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

export function trackEvent(
  type: string,
  page: string,
  intent?: string,
  metadata?: Record<string, unknown>,
): void {
  const body: Record<string, unknown> = {
    event_type: type,
    session_id: getSessionId(),
    page,
  }
  if (intent) body.intent = intent
  if (metadata) body.metadata = metadata

  // Fire and forget — don't block UI
  api.post('/analytics/event', body).catch(() => {
    // Silently ignore analytics failures
  })
}
