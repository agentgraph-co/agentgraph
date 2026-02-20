import { useEffect } from 'react'

export function useUnsavedChanges(hasChanges: boolean) {
  // Handle browser close / tab close / refresh
  useEffect(() => {
    if (!hasChanges) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [hasChanges])
}
