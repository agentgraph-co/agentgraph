import { useEffect, useCallback } from 'react'
import { useBlocker } from 'react-router-dom'

export function useUnsavedChanges(hasChanges: boolean) {
  // Block react-router navigation
  const blocker = useBlocker(hasChanges)

  // Handle browser close / tab close / refresh
  useEffect(() => {
    if (!hasChanges) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [hasChanges])

  // Auto-confirm via window.confirm when blocker triggers
  const confirmNavigation = useCallback(() => {
    if (blocker.state === 'blocked') {
      blocker.proceed()
    }
  }, [blocker])

  const cancelNavigation = useCallback(() => {
    if (blocker.state === 'blocked') {
      blocker.reset()
    }
  }, [blocker])

  // Show native confirm dialog when blocked
  useEffect(() => {
    if (blocker.state === 'blocked') {
      const confirmed = window.confirm('You have unsaved changes. Are you sure you want to leave?')
      if (confirmed) {
        blocker.proceed()
      } else {
        blocker.reset()
      }
    }
  }, [blocker])

  return { blocker, confirmNavigation, cancelNavigation }
}
