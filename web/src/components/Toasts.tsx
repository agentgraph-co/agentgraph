import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react'

interface Toast {
  id: number
  message: string
  type: 'info' | 'success' | 'error'
}

interface ToastContextType {
  addToast: (message: string, type?: Toast['type']) => void
}

const ToastContext = createContext<ToastContextType>({ addToast: () => {} })

let nextId = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = useCallback((message: string, type: Toast['type'] = 'info') => {
    const id = nextId++
    setToasts((prev) => [...prev, { id, message, type }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 4000)
  }, [])

  useEffect(() => {
    const handler = () => addToast('Your session has expired. Please sign in again.', 'error')
    window.addEventListener('session-expired', handler)
    return () => window.removeEventListener('session-expired', handler)
  }, [addToast])

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div className="fixed bottom-4 right-4 flex flex-col gap-2 z-50">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`px-4 py-2 rounded-lg text-sm shadow-lg animate-slide-in ${
              toast.type === 'error'
                ? 'bg-danger text-white'
                : toast.type === 'success'
                  ? 'bg-success text-white'
                  : 'bg-surface border border-border text-text'
            }`}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}
