import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import api from '../../lib/api'
import { useToast } from '../../components/Toasts'
import { InlineSkeleton } from '../../components/Skeleton'
import type {
  RedditThread,
  RedditDraftResult,
  HFDiscussion,
  HFDraftResult,
} from './types'

export default function ScoutTab() {
  const { addToast } = useToast()
  const [redditDraft, setRedditDraft] = useState<RedditDraftResult | null>(null)
  const [redditDraftContext, setRedditDraftContext] = useState('')
  const [generatingDraftFor, setGeneratingDraftFor] = useState<string | null>(null)
  const [hfDraft, setHfDraft] = useState<HFDraftResult | null>(null)
  const [hfDraftContext, setHfDraftContext] = useState('')
  const [generatingHfDraftFor, setGeneratingHfDraftFor] = useState<string | null>(null)
  const [hfForceRefresh, setHfForceRefresh] = useState(false)

  const { data: redditThreads, isLoading: redditLoading, refetch: refetchReddit } = useQuery<RedditThread[]>({
    queryKey: ['admin-reddit-threads'],
    queryFn: async () => (await api.get('/admin/marketing/reddit/threads')).data,
    staleTime: 5 * 60_000,
  })

  const generateRedditDraftMutation = useMutation({
    mutationFn: async ({ threadUrl, context }: { threadUrl: string; context?: string }) => {
      return (await api.post('/admin/marketing/reddit/generate-draft', {
        thread_url: threadUrl,
        context: context || undefined,
      })).data as RedditDraftResult
    },
    onSuccess: (data) => {
      setRedditDraft(data)
      setGeneratingDraftFor(null)
      setRedditDraftContext('')
      addToast('Reddit draft generated', 'success')
    },
    onError: () => {
      setGeneratingDraftFor(null)
      addToast('Failed to generate draft', 'error')
    },
  })

  const { data: hfDiscussions, isLoading: hfLoading } = useQuery<HFDiscussion[]>({
    queryKey: ['admin-hf-discussions', hfForceRefresh],
    queryFn: async () => {
      const params = hfForceRefresh ? { refresh: 'true' } : {}
      const res = await api.get('/admin/marketing/huggingface/discussions', { params })
      setHfForceRefresh(false)
      return res.data
    },
    staleTime: 5 * 60_000,
  })

  const generateHfDraftMutation = useMutation({
    mutationFn: async ({ repoId, discussionNum, discussionTitle, context }: { repoId: string; discussionNum: number; discussionTitle: string; context?: string }) => {
      return (await api.post('/admin/marketing/huggingface/generate-draft', {
        repo_id: repoId,
        discussion_num: discussionNum,
        discussion_title: discussionTitle,
        context: context || undefined,
      })).data as HFDraftResult
    },
    onSuccess: (data) => {
      setHfDraft(data)
      setGeneratingHfDraftFor(null)
      setHfDraftContext('')
      addToast('HuggingFace draft generated', 'success')
    },
    onError: () => {
      setGeneratingHfDraftFor(null)
      addToast('Failed to generate draft', 'error')
    },
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">Discovery — Threads to Engage</h2>
        <button
          onClick={() => { refetchReddit(); setHfForceRefresh(true) }}
          disabled={redditLoading || hfLoading}
          className="text-xs bg-primary/10 text-primary hover:bg-primary/20 px-3 py-1.5 rounded cursor-pointer disabled:opacity-50"
        >
          {(redditLoading || hfLoading) ? 'Scanning...' : 'Refresh Scan'}
        </button>
      </div>
      <p className="text-xs text-text-muted mb-3">
        Reddit threads and HuggingFace discussions relevant to AI agents, trust, and identity. Generate a draft reply for any thread.
      </p>

      {/* Reddit Threads */}
      {redditLoading ? (
        <div className="py-6"><InlineSkeleton /></div>
      ) : redditThreads && redditThreads.length > 0 ? (
        <div className="space-y-2">
          {redditThreads.map((thread) => (
            <div key={thread.url} className="bg-surface border border-border rounded-lg p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <a
                    href={thread.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-medium text-indigo-400 hover:text-indigo-300 hover:underline leading-snug"
                  >
                    {thread.title}
                  </a>
                  <div className="flex flex-wrap gap-2 mt-1.5 text-[10px] text-text-muted">
                    <span className="font-medium text-primary bg-primary/10 px-1.5 py-0.5 rounded">r/{thread.subreddit}</span>
                    {thread.ranking_score != null && (
                      <span className="font-medium text-success bg-success/10 px-1.5 py-0.5 rounded" title="Actionability score">Rank {thread.ranking_score}</span>
                    )}
                    <span>{thread.score} pts</span>
                    <span>{thread.num_comments} comments</span>
                    <span>u/{thread.author}</span>
                  </div>
                  {thread.selftext_preview && (
                    <div className="text-xs text-text-muted mt-1.5 line-clamp-2">{thread.selftext_preview}</div>
                  )}
                  {thread.keywords_matched.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {thread.keywords_matched.map((kw) => (
                        <span key={kw} className="text-[9px] px-1.5 py-0.5 rounded bg-success/10 text-success">{kw}</span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex-shrink-0">
                  {generatingDraftFor === thread.url ? (
                    <div className="space-y-2 w-48">
                      <input
                        type="text"
                        value={redditDraftContext}
                        onChange={e => setRedditDraftContext(e.target.value)}
                        placeholder="Extra context (optional)"
                        className="w-full text-[10px] bg-surface-hover border border-border rounded px-2 py-1"
                      />
                      <div className="flex gap-1">
                        <button
                          onClick={() => generateRedditDraftMutation.mutate({ threadUrl: thread.url, context: redditDraftContext })}
                          disabled={generateRedditDraftMutation.isPending}
                          className="text-[10px] bg-primary/10 text-primary hover:bg-primary/20 px-2 py-1 rounded cursor-pointer disabled:opacity-50"
                        >
                          {generateRedditDraftMutation.isPending ? 'Generating...' : 'Generate'}
                        </button>
                        <button
                          onClick={() => { setGeneratingDraftFor(null); setRedditDraftContext('') }}
                          className="text-[10px] text-text-muted hover:text-text px-2 py-1 cursor-pointer"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      onClick={() => setGeneratingDraftFor(thread.url)}
                      className="text-[10px] bg-primary/10 text-primary hover:bg-primary/20 px-2 py-1 rounded cursor-pointer whitespace-nowrap"
                    >
                      Generate Draft
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-xs text-text-muted bg-surface border border-border rounded-lg p-4 text-center">
          No relevant Reddit threads found.
        </div>
      )}

      {/* HuggingFace Discussions */}
      <div className="mt-4">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-yellow-400" />
          HuggingFace Model Discussions
        </h3>
        {hfLoading ? (
          <div className="py-4"><InlineSkeleton /></div>
        ) : hfDiscussions && hfDiscussions.length > 0 ? (
          <div className="space-y-2">
            {hfDiscussions.map((disc) => {
              const discKey = `${disc.repo_id}/${disc.discussion_num}`
              return (
                <div key={discKey} className="bg-surface border border-border rounded-lg p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <a
                        href={disc.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm font-medium text-yellow-400 hover:text-yellow-300 hover:underline leading-snug"
                      >
                        {disc.title}
                      </a>
                      <div className="flex flex-wrap gap-2 mt-1.5 text-[10px] text-text-muted">
                        <span className="font-medium text-yellow-400 bg-yellow-400/10 px-1.5 py-0.5 rounded">{disc.repo_id}</span>
                        <span>{disc.num_comments} comments</span>
                        <span>{disc.author}</span>
                      </div>
                      {disc.content_preview && (
                        <div className="text-xs text-text-muted mt-1.5 line-clamp-2">{disc.content_preview}</div>
                      )}
                      {disc.keywords_matched.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1.5">
                          {disc.keywords_matched.map((kw) => (
                            <span key={kw} className="text-[9px] px-1.5 py-0.5 rounded bg-success/10 text-success">{kw}</span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex-shrink-0">
                      {generatingHfDraftFor === discKey ? (
                        <div className="space-y-2 w-48">
                          <input
                            type="text"
                            value={hfDraftContext}
                            onChange={e => setHfDraftContext(e.target.value)}
                            placeholder="Extra context (optional)"
                            className="w-full text-[10px] bg-surface-hover border border-border rounded px-2 py-1"
                          />
                          <div className="flex gap-1">
                            <button
                              onClick={() => generateHfDraftMutation.mutate({
                                repoId: disc.repo_id,
                                discussionNum: disc.discussion_num,
                                discussionTitle: disc.title,
                                context: hfDraftContext,
                              })}
                              disabled={generateHfDraftMutation.isPending}
                              className="text-[10px] bg-yellow-400/10 text-yellow-400 hover:bg-yellow-400/20 px-2 py-1 rounded cursor-pointer disabled:opacity-50"
                            >
                              {generateHfDraftMutation.isPending ? 'Generating...' : 'Generate'}
                            </button>
                            <button
                              onClick={() => { setGeneratingHfDraftFor(null); setHfDraftContext('') }}
                              className="text-[10px] text-text-muted hover:text-text px-2 py-1 cursor-pointer"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <button
                          onClick={() => setGeneratingHfDraftFor(discKey)}
                          className="text-[10px] bg-yellow-400/10 text-yellow-400 hover:bg-yellow-400/20 px-2 py-1 rounded cursor-pointer whitespace-nowrap"
                        >
                          Generate Draft
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="text-xs text-text-muted bg-surface border border-border rounded-lg p-4 text-center">
            No relevant HuggingFace discussions found.
          </div>
        )}
      </div>

      {/* Reddit Draft Modal */}
      {redditDraft && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setRedditDraft(null)}>
          <div className="bg-surface border border-border rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] overflow-y-auto m-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-4 border-b border-border">
              <div>
                <h3 className="text-sm font-semibold">Reddit Draft Reply</h3>
                <div className="text-xs text-text-muted mt-0.5 truncate max-w-md">{redditDraft.thread_title}</div>
              </div>
              <button onClick={() => setRedditDraft(null)} className="text-text-muted hover:text-text text-lg cursor-pointer">&times;</button>
            </div>
            <div className="p-4">
              <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed">{redditDraft.draft_content}</pre>
            </div>
            <div className="flex items-center justify-between p-4 border-t border-border">
              <div className="text-[10px] text-text-muted">
                {redditDraft.llm_model && <span>Model: {redditDraft.llm_model}</span>}
                {redditDraft.llm_cost_usd > 0 && <span className="ml-2">Cost: ${redditDraft.llm_cost_usd.toFixed(4)}</span>}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(redditDraft.draft_content)
                    addToast('Draft copied to clipboard', 'success')
                  }}
                  className="text-xs bg-primary/10 text-primary hover:bg-primary/20 px-4 py-2 rounded cursor-pointer"
                >
                  Copy to Clipboard
                </button>
                <a
                  href={redditDraft.thread_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs bg-surface-hover text-text-muted hover:text-text px-4 py-2 rounded inline-flex items-center"
                >
                  Open Thread
                </a>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* HuggingFace Draft Modal */}
      {hfDraft && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setHfDraft(null)}>
          <div className="bg-surface border border-border rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] overflow-y-auto m-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-4 border-b border-border">
              <div>
                <h3 className="text-sm font-semibold">HuggingFace Draft Reply</h3>
                <div className="text-xs text-text-muted mt-0.5 truncate max-w-md">{hfDraft.repo_id} — {hfDraft.discussion_title}</div>
              </div>
              <button onClick={() => setHfDraft(null)} className="text-text-muted hover:text-text text-lg cursor-pointer">&times;</button>
            </div>
            <div className="p-4">
              <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed">{hfDraft.draft_content}</pre>
            </div>
            <div className="flex items-center justify-between p-4 border-t border-border">
              <div className="text-[10px] text-text-muted">
                {hfDraft.llm_model && <span>Model: {hfDraft.llm_model}</span>}
                {hfDraft.llm_cost_usd > 0 && <span className="ml-2">Cost: ${hfDraft.llm_cost_usd.toFixed(4)}</span>}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(hfDraft.draft_content)
                    addToast('Draft copied to clipboard', 'success')
                  }}
                  className="text-xs bg-yellow-400/10 text-yellow-400 hover:bg-yellow-400/20 px-4 py-2 rounded cursor-pointer"
                >
                  Copy to Clipboard
                </button>
                <a
                  href={`https://huggingface.co/${hfDraft.repo_id}/discussions`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs bg-surface-hover text-text-muted hover:text-text px-4 py-2 rounded inline-flex items-center"
                >
                  Open Discussion
                </a>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
