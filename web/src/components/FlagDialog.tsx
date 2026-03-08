import { useState, useEffect, useRef, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import api from '../lib/api'
import { useToast } from './Toasts'

const REASONS = [
  { value: 'spam', label: 'Spam' },
  { value: 'harassment', label: 'Harassment' },
  { value: 'misinformation', label: 'Misinformation' },
  { value: 'illegal', label: 'Illegal Content' },
  { value: 'off_topic', label: 'Off Topic' },
  { value: 'trust_contestation', label: 'Trust Contestation' },
  { value: 'other', label: 'Other' },
] as const

interface FlagDialogProps {
  targetType: 'post' | 'entity'
  targetId: string
  onClose: () => void
}

export default function FlagDialog({ targetType, targetId, onClose }: FlagDialogProps) {
  const { addToast } = useToast()
  const dialogRef = useRef<HTMLDivElement>(null)
  const [reason, setReason] = useState('spam')
  const [details, setDetails] = useState('')

  const flagMutation = useMutation({
    mutationFn: async () => {
      await api.post('/moderation/flag', {
        target_type: targetType,
        target_id: targetId,
        reason,
        details: details || null,
      })
    },
    onSuccess: () => {
      addToast('Report submitted', 'success')
      onClose()
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      addToast(msg || 'Failed to submit report', 'error')
    },
  })

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
        return
      }
      if (e.key === 'Tab' && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          'input, textarea, button:not([disabled]), select'
        )
        if (focusable.length === 0) return
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    flagMutation.mutate()
  }

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="flag-dialog-title"
    >
      <div ref={dialogRef} className="bg-surface border border-border rounded-lg p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h3 id="flag-dialog-title" className="text-lg font-bold mb-4">
          Report {targetType === 'post' ? 'Post' : 'User'}
        </h3>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-text-muted mb-2">Reason</label>
            <div className="space-y-2">
              {REASONS.map((r) => (
                <label
                  key={r.value}
                  className={`flex items-center gap-2 p-2 rounded cursor-pointer border transition-colors ${
                    reason === r.value
                      ? 'border-primary bg-primary/10'
                      : 'border-transparent hover:bg-surface-hover'
                  }`}
                >
                  <input
                    type="radio"
                    name="reason"
                    value={r.value}
                    checked={reason === r.value}
                    onChange={() => setReason(r.value)}
                    className="accent-primary"
                  />
                  <span className="text-sm">{r.label}</span>
                </label>
              ))}
            </div>
          </div>
          <div>
            <label htmlFor="flag-details" className="block text-sm text-text-muted mb-1">Details (optional)</label>
            <textarea
              id="flag-details"
              value={details}
              onChange={(e) => setDetails(e.target.value)}
              rows={3}
              maxLength={2000}
              placeholder="Provide additional context..."
              className="w-full bg-background border border-border rounded-md px-3 py-2 text-text text-sm focus:outline-none focus:border-primary resize-none"
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 text-sm border border-border rounded-md hover:bg-surface-hover transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={flagMutation.isPending}
              className="bg-danger hover:bg-danger/80 text-white px-4 py-1.5 rounded-md text-sm transition-colors disabled:opacity-50 cursor-pointer"
            >
              {flagMutation.isPending ? 'Submitting...' : 'Submit Report'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
