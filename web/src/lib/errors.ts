/**
 * Extract a human-readable error message from an API error response.
 *
 * Handles the common axios error shape where the backend returns
 * `{ detail: "..." }` in the response body.
 */
export function getApiErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: string } } })
    ?.response?.data?.detail
  return detail || fallback
}
