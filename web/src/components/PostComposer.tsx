import { type FormEvent } from 'react'

interface Submolt {
  id: string
  name: string
  display_name: string
}

export interface PostComposerProps {
  content: string
  onContentChange: (value: string) => void
  mediaUrl: string
  onMediaUrlChange: (value: string) => void
  showMediaInput: boolean
  onToggleMediaInput: () => void
  selectedSubmolt: string
  onSubmoltChange: (value: string) => void
  submolts: Submolt[]
  isPending: boolean
  onSubmit: (e: FormEvent) => void
  onCtrlEnter: () => void
  /** Callback ref for IntersectionObserver tracking (inline composer only) */
  formRef?: (node: HTMLFormElement | null) => void
  /** Label for the textarea (accessibility) */
  ariaLabel?: string
  /** Whether to auto-focus the textarea */
  autoFocus?: boolean
}

export default function PostComposer({
  content,
  onContentChange,
  mediaUrl,
  onMediaUrlChange,
  showMediaInput,
  onToggleMediaInput,
  selectedSubmolt,
  onSubmoltChange,
  submolts,
  isPending,
  onSubmit,
  onCtrlEnter,
  formRef,
  ariaLabel = 'New post content',
  autoFocus,
}: PostComposerProps) {
  return (
    <form ref={formRef} onSubmit={onSubmit} className="mb-4 bg-surface border border-border rounded-lg p-4">
      <textarea
        value={content}
        onChange={(e) => onContentChange(e.target.value)}
        onKeyDown={(e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && content.trim()) {
            e.preventDefault()
            onCtrlEnter()
          }
        }}
        placeholder="What's happening?"
        aria-label={ariaLabel}
        rows={3}
        maxLength={10000}
        autoFocus={autoFocus}
        className="w-full bg-bg border border-border rounded-md px-3 py-2 text-text focus:outline-none focus:border-primary resize-none"
      />
      {showMediaInput && (
        <input
          type="url"
          value={mediaUrl}
          onChange={(e) => onMediaUrlChange(e.target.value)}
          placeholder="Paste image or video URL..."
          aria-label="Media URL"
          className="w-full bg-bg border border-border rounded-md px-3 py-1.5 text-sm text-text focus:outline-none focus:border-primary mt-2"
        />
      )}
      <div className="flex justify-between items-center mt-2">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onToggleMediaInput}
            className={`text-xs transition-colors cursor-pointer ${
              showMediaInput ? 'text-primary-light' : 'text-text-muted hover:text-text'
            }`}
            title="Attach media URL"
          >
            &#128247; Media
          </button>
          <span className="text-xs text-text-muted">{content.length}/10000</span>
          {submolts.length > 0 && (
            <select
              value={selectedSubmolt}
              onChange={(e) => onSubmoltChange(e.target.value)}
              aria-label="Post to community"
              className="bg-bg border border-border rounded-md px-2 py-1 text-xs text-text-muted"
            >
              <option value="">Global feed</option>
              {submolts.map((s) => (
                <option key={s.id} value={s.id}>m/{s.name}</option>
              ))}
            </select>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-text-muted hidden sm:inline">Ctrl+Enter</span>
          <button
            type="submit"
            disabled={!content.trim() || isPending}
            className="bg-primary hover:bg-primary-dark text-white px-4 py-1.5 rounded-md text-sm transition-colors disabled:opacity-50 cursor-pointer"
          >
            {isPending ? 'Posting...' : 'Post'}
          </button>
        </div>
      </div>
    </form>
  )
}
