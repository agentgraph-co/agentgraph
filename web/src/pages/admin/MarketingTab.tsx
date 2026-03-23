import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { useToast } from '../../components/Toasts'
import { timeAgo } from '../../lib/formatters'
import { InlineSkeleton } from '../../components/Skeleton'
import { StatCard } from './StatCard'
import { PLATFORM_DESTINATIONS } from './types'
import type {
  MarketingDashboard,
  MarketingDraft,
  MarketingHealth,
  CampaignProposal,
  CampaignDetail,
  RedditThread,
  RedditDraftResult,
  HFDiscussion,
  HFDraftResult,
  ActivityItem,
  BotActivity,
} from './types'

export default function MarketingTab() {
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [draftEditContent, setDraftEditContent] = useState('')
  const [editingDraftId, setEditingDraftId] = useState<string | null>(null)
  const [draftPlatformFilter, setDraftPlatformFilter] = useState<string>('')
  const [draftStatusFilter, setDraftStatusFilter] = useState<string>('human_review')
  const [previewDraft, setPreviewDraft] = useState<MarketingDraft | null>(null)
  const [expandedCampaignId, setExpandedCampaignId] = useState<string | null>(null)
  const [campaignDeselected, setCampaignDeselected] = useState<Set<number>>(new Set())
  const [rejectFeedback, setRejectFeedback] = useState('')
  const [rejectingCampaignId, setRejectingCampaignId] = useState<string | null>(null)
  const [redditDraft, setRedditDraft] = useState<RedditDraftResult | null>(null)
  const [redditDraftContext, setRedditDraftContext] = useState('')
  const [generatingDraftFor, setGeneratingDraftFor] = useState<string | null>(null)
  const [hfDraft, setHfDraft] = useState<HFDraftResult | null>(null)
  const [hfDraftContext, setHfDraftContext] = useState('')
  const [generatingHfDraftFor, setGeneratingHfDraftFor] = useState<string | null>(null)
  const [activityFilter, setActivityFilter] = useState<'all' | 'posted' | 'pending' | 'failed'>('all')
  const [hfForceRefresh, setHfForceRefresh] = useState(false)

  const { data: mktDashboard, isLoading: mktLoading } = useQuery<MarketingDashboard>({
    queryKey: ['admin-marketing-dashboard'],
    queryFn: async () => (await api.get('/admin/marketing/dashboard')).data,
    staleTime: 2 * 60_000,
  })

  const { data: mktDrafts } = useQuery<MarketingDraft[]>({
    queryKey: ['admin-marketing-drafts', draftPlatformFilter, draftStatusFilter],
    queryFn: async () => {
      const params: Record<string, string> = {}
      if (draftPlatformFilter) params.platform = draftPlatformFilter
      if (draftStatusFilter) params.status = draftStatusFilter
      else params.status = 'human_review,draft,planned'
      return (await api.get('/admin/marketing/drafts', { params })).data
    },
    staleTime: 30_000,
  })

  const { data: mktHealth } = useQuery<MarketingHealth>({
    queryKey: ['admin-marketing-health'],
    queryFn: async () => (await api.get('/admin/marketing/health')).data,
    staleTime: 60_000,
  })

  const draftActionMutation = useMutation({
    mutationFn: async ({ postId, action, content }: { postId: string; action: string; content?: string }) => {
      return (await api.post(`/admin/marketing/drafts/${postId}`, { action, content })).data
    },
    onSuccess: (_data, vars) => {
      addToast(`Draft ${vars.action === 'approve' ? 'approved' : vars.action === 'reject' ? 'rejected' : 'edited & approved'}`, 'success')
      setEditingDraftId(null)
      setDraftEditContent('')
      queryClient.invalidateQueries({ queryKey: ['admin-marketing-drafts'] })
      queryClient.invalidateQueries({ queryKey: ['admin-marketing-dashboard'] })
    },
    onError: () => { addToast('Failed to update draft', 'error') },
  })

  const triggerMarketingMutation = useMutation({
    mutationFn: async () => (await api.post('/admin/marketing/trigger')).data,
    onSuccess: () => {
      addToast('Marketing tick triggered', 'success')
      queryClient.invalidateQueries({ queryKey: ['admin-marketing-dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['admin-marketing-drafts'] })
    },
    onError: () => { addToast('Failed to trigger marketing tick', 'error') },
  })

  const triggerPlatformMutation = useMutation({
    mutationFn: async (platform: string) => (await api.post(`/admin/marketing/trigger/${platform}`)).data,
    onSuccess: (data: Record<string, unknown>, platform: string) => {
      addToast(`Draft created for ${platform}`, 'success')
      queryClient.invalidateQueries({ queryKey: ['admin-marketing-drafts'] })
      queryClient.invalidateQueries({ queryKey: ['admin-marketing-dashboard'] })
      // Show preview modal if draft content was returned
      if (data.draft && typeof data.draft === 'object') {
        const d = data.draft as Record<string, unknown>
        setPreviewDraft({
          id: String(d.id ?? ''),
          platform: String(d.platform ?? ''),
          content: String(d.content ?? ''),
          topic: d.topic ? String(d.topic) : null,
          post_type: String(d.post_type ?? ''),
          status: String(d.status ?? ''),
          llm_model: d.llm_model ? String(d.llm_model) : null,
          created_at: String(d.created_at ?? ''),
          image_url: d.image_url ? String(d.image_url) : null,
          destination: d.destination ? String(d.destination) : null,
          parent_external_id: d.parent_external_id ? String(d.parent_external_id) : null,
        })
      }
    },
    onError: (_err, platform) => { addToast(`Failed to trigger ${platform}`, 'error') },
  })

  const { data: proposedCampaigns, refetch: refetchCampaigns } = useQuery<CampaignProposal[]>({
    queryKey: ['admin-campaigns-proposed'],
    queryFn: async () => (await api.get('/admin/marketing/campaigns/proposed')).data,
    staleTime: 30_000,
  })

  const { data: expandedCampaign } = useQuery<CampaignDetail>({
    queryKey: ['admin-campaign-detail', expandedCampaignId],
    queryFn: async () => (await api.get(`/admin/marketing/campaigns/${expandedCampaignId}`)).data,
    enabled: !!expandedCampaignId,
    staleTime: 30_000,
  })

  const generateCampaignMutation = useMutation({
    mutationFn: async () => (await api.post('/admin/marketing/campaigns/generate', {}, { timeout: 120_000 })).data,
    onSuccess: () => {
      addToast('Campaign plan generated', 'success')
      queryClient.invalidateQueries({ queryKey: ['admin-campaigns-proposed'] })
      queryClient.invalidateQueries({ queryKey: ['admin-marketing-dashboard'] })
    },
    onError: () => { addToast('Failed to generate campaign plan', 'error') },
  })

  const approveCampaignMutation = useMutation({
    mutationFn: async ({ campaignId, approvedIndices }: { campaignId: string; approvedIndices?: number[] }) => {
      return (await api.post(`/admin/marketing/campaigns/${campaignId}/approve`, approvedIndices ? { approved_post_indices: approvedIndices } : {})).data
    },
    onSuccess: () => {
      addToast('Campaign approved', 'success')
      setExpandedCampaignId(null)
      setCampaignDeselected(new Set())
      refetchCampaigns()
      queryClient.invalidateQueries({ queryKey: ['admin-marketing-dashboard'] })
    },
    onError: () => { addToast('Failed to approve campaign', 'error') },
  })

  const rejectCampaignMutation = useMutation({
    mutationFn: async ({ campaignId, feedback }: { campaignId: string; feedback: string }) => {
      return (await api.post(`/admin/marketing/campaigns/${campaignId}/reject`, { feedback })).data
    },
    onSuccess: () => {
      addToast('Campaign rejected', 'success')
      setExpandedCampaignId(null)
      setRejectingCampaignId(null)
      setRejectFeedback('')
      refetchCampaigns()
    },
    onError: () => { addToast('Failed to reject campaign', 'error') },
  })

  // ─── Reddit Scout queries ───

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

  // ─── HuggingFace Scout queries ───

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

  // ─── Bot Activity query ───

  const { data: botActivity, isLoading: activityLoading } = useQuery<BotActivity>({
    queryKey: ['admin-bot-activity'],
    queryFn: async () => (await api.get('/admin/marketing/activity')).data,
    staleTime: 30_000,
  })

  return (
    <div className="space-y-6">
      {mktLoading ? (
        <div className="py-10"><InlineSkeleton /></div>
      ) : (
        <>
          {/* Health & Controls */}
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => triggerMarketingMutation.mutate()}
              disabled={triggerMarketingMutation.isPending}
              className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-md text-sm transition-colors disabled:opacity-50 cursor-pointer"
            >
              {triggerMarketingMutation.isPending ? 'Running...' : 'Trigger Marketing Tick'}
            </button>
            {mktHealth && (
              <div className="flex flex-wrap gap-2 text-xs">
                <span className={`px-2 py-1 rounded ${mktHealth.marketing_enabled ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger'}`}>
                  {mktHealth.marketing_enabled ? 'Enabled' : 'Disabled'}
                </span>
                <span className={`px-2 py-1 rounded ${mktHealth.anthropic_configured ? 'bg-success/10 text-success' : 'bg-warning/10 text-warning'}`}>
                  {mktHealth.anthropic_configured ? 'Anthropic OK' : 'No Anthropic Key'}
                </span>
                <span className={`px-2 py-1 rounded ${mktHealth.ollama_available ? 'bg-success/10 text-success' : 'bg-surface-hover text-text-muted'}`}>
                  {mktHealth.ollama_available ? 'Ollama OK' : 'Ollama Offline'}
                </span>
                <span className="px-2 py-1 rounded bg-surface-hover text-text-muted">
                  Today: ${mktHealth.daily_spend_usd.toFixed(4)}
                </span>
                <span className="px-2 py-1 rounded bg-surface-hover text-text-muted">
                  Month: ${mktHealth.monthly_spend_usd.toFixed(4)}
                </span>
              </div>
            )}
          </div>

          {/* Campaign Planner */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">Campaign Planner</h2>
              <button
                onClick={() => generateCampaignMutation.mutate()}
                disabled={generateCampaignMutation.isPending}
                className="text-xs bg-primary/10 text-primary hover:bg-primary/20 px-3 py-1.5 rounded cursor-pointer disabled:opacity-50"
              >
                {generateCampaignMutation.isPending ? 'Generating...' : 'Generate Weekly Plan'}
              </button>
            </div>

            {proposedCampaigns && proposedCampaigns.length > 0 ? (
              <div className="space-y-3">
                {proposedCampaigns.map((campaign) => (
                  <div key={campaign.id} className="bg-surface border border-border rounded-lg overflow-hidden">
                    {/* Campaign header */}
                    <button
                      onClick={() => {
                        if (expandedCampaignId === campaign.id) {
                          setExpandedCampaignId(null)
                        } else {
                          setExpandedCampaignId(campaign.id)
                          setCampaignDeselected(new Set())
                          setRejectingCampaignId(null)
                        }
                      }}
                      className="w-full flex items-center justify-between p-4 text-left hover:bg-surface-hover/50 transition-colors cursor-pointer"
                    >
                      <div>
                        <div className="text-sm font-medium">{campaign.name}</div>
                        <div className="text-xs text-text-muted mt-0.5">
                          {campaign.platforms.map(p => p.charAt(0).toUpperCase() + p.slice(1)).join(', ')}
                          {campaign.start_date && <span className="ml-2">| Starts {campaign.start_date}</span>}
                        </div>
                      </div>
                      <span className="text-xs px-2 py-1 rounded bg-warning/10 text-warning">Proposed</span>
                    </button>

                    {/* Expanded campaign detail */}
                    {expandedCampaignId === campaign.id && expandedCampaign && (
                      <div className="border-t border-border p-4 space-y-4">
                        {/* Strategy summary */}
                        {expandedCampaign.schedule_config?.strategy_summary && (
                          <div className="text-sm text-text-muted bg-surface-hover/50 rounded-lg p-3">
                            {expandedCampaign.schedule_config.strategy_summary}
                          </div>
                        )}

                        {/* News hooks */}
                        {expandedCampaign.schedule_config?.news_hooks && expandedCampaign.schedule_config.news_hooks.length > 0 && (
                          <div>
                            <div className="text-xs font-semibold text-text-muted mb-2">News Hooks</div>
                            <div className="flex flex-wrap gap-2">
                              {expandedCampaign.schedule_config.news_hooks.map((h, i) => (
                                <span key={i} className="text-[10px] px-2 py-1 rounded bg-primary/10 text-primary">{h.title}</span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Planned posts with checkboxes */}
                        {expandedCampaign.schedule_config?.posts && (
                          <div>
                            <div className="text-xs font-semibold text-text-muted mb-2">
                              Planned Posts ({expandedCampaign.schedule_config.posts.length - campaignDeselected.size} of {expandedCampaign.schedule_config.posts.length} selected)
                            </div>
                            <div className="space-y-2">
                              {expandedCampaign.schedule_config.posts.map((post, idx) => (
                                <label key={idx} className={`flex gap-3 p-3 rounded-lg border transition-colors cursor-pointer ${campaignDeselected.has(idx) ? 'border-border/50 opacity-50' : 'border-border bg-surface-hover/30'}`}>
                                  <input
                                    type="checkbox"
                                    checked={!campaignDeselected.has(idx)}
                                    onChange={() => {
                                      const next = new Set(campaignDeselected)
                                      if (next.has(idx)) next.delete(idx)
                                      else next.add(idx)
                                      setCampaignDeselected(next)
                                    }}
                                    className="mt-0.5 accent-primary"
                                  />
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                      <span className="text-xs font-medium capitalize bg-primary/10 text-primary px-1.5 py-0.5 rounded">{post.platform}</span>
                                      {post.day && <span className="text-[10px] text-text-muted capitalize">{post.day}</span>}
                                      {post.value_type && <span className="text-[10px] text-text-muted/60">{post.value_type.replace('_', ' ')}</span>}
                                    </div>
                                    <div className="text-sm mt-1">{post.topic}</div>
                                    <div className="text-xs text-text-muted mt-0.5">{post.angle}</div>
                                    {post.why && <div className="text-[10px] text-text-muted/60 mt-1 italic">{post.why}</div>}
                                  </div>
                                </label>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Budget + avoid */}
                        <div className="flex flex-wrap gap-4 text-xs text-text-muted">
                          {expandedCampaign.schedule_config?.budget_estimate_usd != null && (
                            <span>Est. budget: ${expandedCampaign.schedule_config.budget_estimate_usd.toFixed(2)}</span>
                          )}
                          {expandedCampaign.schedule_config?.avoid_this_week && expandedCampaign.schedule_config.avoid_this_week.length > 0 && (
                            <span>Avoiding: {expandedCampaign.schedule_config.avoid_this_week.length} topics</span>
                          )}
                        </div>

                        {/* Reject feedback */}
                        {rejectingCampaignId === campaign.id && (
                          <div className="flex gap-2">
                            <input
                              type="text"
                              value={rejectFeedback}
                              onChange={e => setRejectFeedback(e.target.value)}
                              placeholder="Feedback for regeneration..."
                              className="flex-1 text-sm bg-surface-hover border border-border rounded px-3 py-1.5"
                            />
                            <button
                              onClick={() => rejectCampaignMutation.mutate({ campaignId: campaign.id, feedback: rejectFeedback })}
                              disabled={!rejectFeedback.trim() || rejectCampaignMutation.isPending}
                              className="text-xs bg-danger/10 text-danger hover:bg-danger/20 px-3 py-1.5 rounded cursor-pointer disabled:opacity-50"
                            >
                              Confirm Reject
                            </button>
                            <button
                              onClick={() => { setRejectingCampaignId(null); setRejectFeedback('') }}
                              className="text-xs text-text-muted hover:text-text px-2 py-1.5 cursor-pointer"
                            >
                              Cancel
                            </button>
                          </div>
                        )}

                        {/* Approve / Reject buttons */}
                        {rejectingCampaignId !== campaign.id && (
                          <div className="flex gap-2">
                            <button
                              onClick={() => {
                                const totalPosts = expandedCampaign.schedule_config?.posts?.length ?? 0
                                const approvedIndices = Array.from({ length: totalPosts }, (_, i) => i).filter(i => !campaignDeselected.has(i))
                                approveCampaignMutation.mutate({
                                  campaignId: campaign.id,
                                  approvedIndices: campaignDeselected.size > 0 ? approvedIndices : undefined,
                                })
                              }}
                              disabled={approveCampaignMutation.isPending}
                              className="text-xs bg-success/10 text-success hover:bg-success/20 px-4 py-2 rounded cursor-pointer disabled:opacity-50"
                            >
                              {approveCampaignMutation.isPending ? 'Approving...' : `Approve${campaignDeselected.size > 0 ? ` (${(expandedCampaign.schedule_config?.posts?.length ?? 0) - campaignDeselected.size} posts)` : ' All'}`}
                            </button>
                            <button
                              onClick={() => setRejectingCampaignId(campaign.id)}
                              className="text-xs bg-danger/10 text-danger hover:bg-danger/20 px-4 py-2 rounded cursor-pointer"
                            >
                              Reject
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-text-muted bg-surface border border-border rounded-lg p-4 text-center">
                No proposed campaigns. Generate a weekly plan to get started.
              </div>
            )}
          </div>

          {/* Discovery — Reddit + HuggingFace threads to engage with */}
          <div>
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

          {/* Bot Activity Feed */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">Bot Activity</h2>
              <div className="flex gap-1">
                {(['all', 'posted', 'pending', 'failed'] as const).map((f) => (
                  <button
                    key={f}
                    onClick={() => setActivityFilter(f)}
                    className={`text-[10px] px-2 py-1 rounded cursor-pointer transition-colors ${
                      activityFilter === f
                        ? 'bg-primary/20 text-primary'
                        : 'bg-surface-hover text-text-muted hover:text-text'
                    }`}
                  >
                    {f === 'all' ? `All${botActivity ? ` (${botActivity.total})` : ''}` :
                     f === 'posted' ? `Posted${botActivity ? ` (${botActivity.posted.length})` : ''}` :
                     f === 'pending' ? `Pending${botActivity ? ` (${botActivity.pending_review.length})` : ''}` :
                     `Failed${botActivity ? ` (${botActivity.failed.length})` : ''}`}
                  </button>
                ))}
              </div>
            </div>
            {activityLoading ? (
              <div className="py-6"><InlineSkeleton /></div>
            ) : botActivity ? (() => {
              const items: ActivityItem[] =
                activityFilter === 'posted' ? botActivity.posted :
                activityFilter === 'pending' ? botActivity.pending_review :
                activityFilter === 'failed' ? botActivity.failed :
                [...botActivity.posted, ...botActivity.pending_review, ...botActivity.failed]
                  .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
              const platformColors: Record<string, string> = {
                twitter: 'bg-blue-500/10 text-blue-400',
                reddit: 'bg-orange-500/10 text-orange-400',
                bluesky: 'bg-sky-400/10 text-sky-400',
                huggingface: 'bg-yellow-400/10 text-yellow-400',
                devto: 'bg-gray-400/10 text-gray-400',
                discord: 'bg-indigo-500/10 text-indigo-400',
                linkedin: 'bg-blue-600/10 text-blue-500',
                telegram: 'bg-cyan-500/10 text-cyan-400',
                hashnode: 'bg-blue-400/10 text-blue-300',
                hackernews: 'bg-orange-600/10 text-orange-500',
                github_discussions: 'bg-gray-500/10 text-gray-300',
              }
              const statusBadge = (s: string) =>
                s === 'posted' ? 'bg-success/10 text-success' :
                s === 'human_review' ? 'bg-warning/10 text-warning' :
                s === 'failed' ? 'bg-danger/10 text-danger' :
                'bg-surface-hover text-text-muted'
              return items.length > 0 ? (
                <div className="space-y-2">
                  {items.map((item) => (
                    <div key={item.id} className="bg-surface border border-border rounded-lg p-3 flex items-start gap-3">
                      <div className="flex-shrink-0 mt-0.5">
                        <span className={`text-[10px] font-medium capitalize px-1.5 py-0.5 rounded ${platformColors[item.platform] || 'bg-surface-hover text-text-muted'}`}>
                          {item.platform}
                        </span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs leading-relaxed text-text/80 line-clamp-2">{item.content_preview}</div>
                        <div className="flex flex-wrap gap-2 mt-1.5 text-[10px] text-text-muted">
                          <span className={`px-1.5 py-0.5 rounded ${statusBadge(item.status)}`}>
                            {item.status === 'human_review' ? 'Pending Review' : item.status}
                          </span>
                          {item.topic && <span className="bg-surface-hover px-1.5 py-0.5 rounded capitalize">{item.topic}</span>}
                          <span>{timeAgo(item.created_at)}</span>
                        </div>
                      </div>
                      {item.external_id && (
                        <a
                          href={
                            item.platform === 'twitter' ? `https://twitter.com/i/web/status/${item.external_id}` :
                            item.platform === 'bluesky' ? `https://bsky.app/profile/agentgraph.bsky.social/post/${item.external_id}` :
                            item.platform === 'reddit' ? `https://old.reddit.com${item.external_id}` :
                            item.platform === 'devto' ? `https://dev.to/agentgraph/${item.external_id}` :
                            '#'
                          }
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex-shrink-0 text-[10px] text-primary hover:text-primary-light"
                        >
                          View
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-text-muted bg-surface border border-border rounded-lg p-4 text-center">
                  No activity in this category.
                </div>
              )
            })() : null}
          </div>

          {/* Stats Cards */}
          {mktDashboard && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard label="Total Posts" value={mktDashboard.recent_posts.length} sub="Last 7 days" />
              <StatCard label="Pending Drafts" value={mktDashboard.pending_drafts} sub={mktDashboard.pending_drafts > 0 ? 'Needs review' : 'All clear'} />
              <StatCard label="LLM Spend (today)" value={`$${mktDashboard.cost.daily_spend_usd.toFixed(4)}`} sub={`Month: $${mktDashboard.cost.monthly_spend_usd.toFixed(4)}`} />
              <StatCard
                label="Engagement"
                value={(mktDashboard.engagement.total_likes + mktDashboard.engagement.total_comments + mktDashboard.engagement.total_shares).toLocaleString()}
                sub="Likes + comments + shares"
              />
            </div>
          )}

          {/* Platform Adapters */}
          {mktHealth && (
            <div>
              <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">Platform Adapters</h2>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                {Object.entries(mktHealth.adapters).map(([name, info]) => (
                  <div key={name} className="bg-surface border border-border rounded-lg p-3 text-center">
                    <div className="text-xs font-medium capitalize">{name}</div>
                    <div className="mt-1">
                      {info.configured ? (
                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${info.healthy ? 'bg-success/10 text-success' : 'bg-warning/10 text-warning'}`}>
                          {info.healthy ? 'Healthy' : 'Unhealthy'}
                        </span>
                      ) : (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-hover text-text-muted">Not configured</span>
                      )}
                    </div>
                    {info.configured && (
                      <button
                        onClick={() => triggerPlatformMutation.mutate(name)}
                        disabled={triggerPlatformMutation.isPending}
                        className="mt-2 text-[10px] bg-primary/10 text-primary hover:bg-primary/20 px-2 py-1 rounded cursor-pointer disabled:opacity-50"
                      >
                        Generate Draft
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Posts by Platform */}
          {mktDashboard && mktDashboard.platform_stats.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">Posts by Platform</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {mktDashboard.platform_stats.map((ps) => (
                  <div key={ps.platform} className="bg-surface border border-border rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium capitalize">{ps.platform}</span>
                      <span className="text-sm font-medium">{ps.total}</span>
                    </div>
                    <div className="flex gap-2 text-[10px] text-text-muted">
                      <span className="text-success">{ps.posted} posted</span>
                      {ps.failed > 0 && <span className="text-danger">{ps.failed} failed</span>}
                      {ps.pending_review > 0 && <span className="text-warning">{ps.pending_review} review</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Cost Breakdown */}
          {mktDashboard && mktDashboard.cost.breakdown.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">LLM Cost Breakdown</h2>
              <div className="bg-surface border border-border rounded-lg overflow-x-auto">
                <table className="w-full min-w-[400px]">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left text-xs text-text-muted px-4 py-2">Model</th>
                      <th className="text-right text-xs text-text-muted px-4 py-2">Calls</th>
                      <th className="text-right text-xs text-text-muted px-4 py-2">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mktDashboard.cost.breakdown.map((m) => (
                      <tr key={m.model} className="border-b border-border/50">
                        <td className="text-xs px-4 py-2">{m.model}</td>
                        <td className="text-xs px-4 py-2 text-right">{m.calls}</td>
                        <td className="text-xs px-4 py-2 text-right">${m.cost_usd.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Draft Preview Modal — kept for trigger-generated drafts */}
          {previewDraft && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setPreviewDraft(null)}>
              <div className="bg-surface border border-border rounded-lg shadow-xl w-full max-w-3xl max-h-[85vh] overflow-y-auto m-4" onClick={e => e.stopPropagation()}>
                <div className="flex items-center justify-between p-4 border-b border-border">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold">Draft Preview</h3>
                    <span className="text-xs font-medium capitalize bg-primary/10 text-primary px-2 py-0.5 rounded">{previewDraft.platform}</span>
                    <span className="text-[10px] text-text-muted">{PLATFORM_DESTINATIONS[previewDraft.platform] ?? ''}</span>
                    {previewDraft.topic && <span className="text-[10px] bg-surface-hover text-text-muted px-1.5 py-0.5 rounded capitalize">{previewDraft.topic}</span>}
                  </div>
                  <button onClick={() => setPreviewDraft(null)} className="text-text-muted hover:text-text text-lg cursor-pointer">&times;</button>
                </div>
                <div className="p-4 space-y-4">
                  {previewDraft.image_url && (
                    <img src={previewDraft.image_url} alt="Post card" className="w-full max-w-[500px] rounded-lg border border-border" />
                  )}
                  <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed bg-surface-hover rounded-lg p-3">{previewDraft.content}</pre>
                </div>
                <div className="flex gap-2 p-4 border-t border-border">
                  <button
                    onClick={() => { draftActionMutation.mutate({ postId: previewDraft.id, action: 'approve' }); setPreviewDraft(null) }}
                    disabled={draftActionMutation.isPending}
                    className="text-xs bg-success/10 text-success hover:bg-success/20 px-4 py-2 rounded cursor-pointer disabled:opacity-50"
                  >
                    Approve & Post
                  </button>
                  <button
                    onClick={() => { setEditingDraftId(previewDraft.id); setDraftEditContent(previewDraft.content); setPreviewDraft(null) }}
                    className="text-xs bg-surface-hover text-text-muted hover:text-text px-4 py-2 rounded cursor-pointer"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => { draftActionMutation.mutate({ postId: previewDraft.id, action: 'reject' }); setPreviewDraft(null) }}
                    disabled={draftActionMutation.isPending}
                    className="text-xs bg-danger/10 text-danger hover:bg-danger/20 px-4 py-2 rounded cursor-pointer disabled:opacity-50"
                  >
                    Reject
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Drafts Queue */}
          <div>
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
              <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
                Drafts Queue {mktDrafts ? `(${mktDrafts.length})` : ''}
              </h2>
              <div className="flex gap-2">
                <select
                  value={draftStatusFilter}
                  onChange={e => setDraftStatusFilter(e.target.value)}
                  className="text-xs bg-surface-hover border border-border rounded px-2 py-1"
                >
                  <option value="human_review">Needs Review</option>
                  <option value="human_review,draft">Review + Draft</option>
                  <option value="draft">Draft Only</option>
                  <option value="">All</option>
                </select>
                <select
                  value={draftPlatformFilter}
                  onChange={e => setDraftPlatformFilter(e.target.value)}
                  className="text-xs bg-surface-hover border border-border rounded px-2 py-1"
                >
                  <option value="">All Platforms</option>
                  {mktHealth && Object.keys(mktHealth.adapters).map(p => (
                    <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
                  ))}
                </select>
              </div>
            </div>
            {mktDrafts && mktDrafts.length > 0 ? (
              <div className="space-y-3">
                {mktDrafts.map((draft) => (
                  <div key={draft.id} className="bg-surface border border-border rounded-lg p-4">
                    {/* Header: platform badge + destination + status + time */}
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <span className="font-medium capitalize text-xs bg-primary/10 text-primary px-2 py-0.5 rounded">{draft.platform}</span>
                      <span className="text-[10px] text-text-muted">{PLATFORM_DESTINATIONS[draft.platform] ?? draft.platform}</span>
                      {draft.topic && <span className="text-[10px] bg-surface-hover text-text-muted px-1.5 py-0.5 rounded capitalize">{draft.topic}</span>}
                      {draft.post_type === 'reactive' && <span className="text-[10px] bg-warning/10 text-warning px-1.5 py-0.5 rounded">Reply</span>}
                      <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded ${
                        draft.status === 'human_review' ? 'bg-warning/10 text-warning' :
                        draft.status === 'planned' ? 'bg-blue-400/10 text-blue-400' :
                        draft.status === 'draft' ? 'bg-surface-hover text-text-muted' :
                        'bg-primary/10 text-primary'
                      }`}>
                        {draft.status === 'human_review' ? 'Needs Review' : draft.status === 'planned' ? 'Planned' : draft.status}
                      </span>
                      <span className="text-[10px] text-text-muted">{timeAgo(draft.created_at)}</span>
                    </div>

                    {/* Card image preview */}
                    {draft.image_url && (
                      <div className="mb-3">
                        <p className="text-[10px] text-text-muted mb-1.5">Post card image:</p>
                        <img src={draft.image_url} alt="Post card" className="w-full max-w-[400px] rounded-lg border border-border" />
                      </div>
                    )}

                    {/* Content preview */}
                    <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed text-text/80 max-h-[200px] overflow-y-auto bg-surface-hover rounded-lg p-3">{draft.content}</pre>

                    {/* Actions */}
                    <div className="flex gap-2 mt-3 pt-3 border-t border-border/50">
                      <button
                        onClick={() => draftActionMutation.mutate({ postId: draft.id, action: 'approve' })}
                        disabled={draftActionMutation.isPending}
                        className="text-xs bg-success/10 text-success hover:bg-success/20 px-3 py-1.5 rounded cursor-pointer disabled:opacity-50"
                      >
                        Approve & Post
                      </button>
                      <button
                        onClick={() => { setEditingDraftId(draft.id); setDraftEditContent(draft.content) }}
                        className="text-xs bg-surface-hover text-text-muted hover:text-text px-3 py-1.5 rounded cursor-pointer"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => draftActionMutation.mutate({ postId: draft.id, action: 'reject' })}
                        disabled={draftActionMutation.isPending}
                        className="text-xs bg-danger/10 text-danger hover:bg-danger/20 px-3 py-1.5 rounded cursor-pointer disabled:opacity-50"
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-text-muted bg-surface border border-border rounded-lg p-4 text-center">
                No drafts matching the current filter.
              </div>
            )}

            {/* Edit Draft Modal — full-size editor */}
            {editingDraftId && (
              <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => { setEditingDraftId(null); setDraftEditContent('') }}>
                <div className="bg-surface border border-border rounded-lg shadow-xl w-full max-w-3xl max-h-[85vh] overflow-hidden m-4 flex flex-col" onClick={e => e.stopPropagation()}>
                  <div className="flex items-center justify-between p-4 border-b border-border">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold">Edit Draft</h3>
                      {(() => { const d = mktDrafts?.find(x => x.id === editingDraftId); return d ? (
                        <>
                          <span className="text-xs font-medium capitalize bg-primary/10 text-primary px-2 py-0.5 rounded">{d.platform}</span>
                          <span className="text-[10px] text-text-muted">{PLATFORM_DESTINATIONS[d.platform] ?? ''}</span>
                        </>
                      ) : null; })()}
                    </div>
                    <button onClick={() => { setEditingDraftId(null); setDraftEditContent('') }} className="text-text-muted hover:text-text text-lg cursor-pointer">&times;</button>
                  </div>
                  <div className="flex-1 p-4 overflow-y-auto">
                    <textarea
                      value={draftEditContent}
                      onChange={e => setDraftEditContent(e.target.value)}
                      className="w-full text-sm bg-surface-hover border border-border rounded p-3 min-h-[300px] resize-y font-sans leading-relaxed focus:outline-none focus:border-primary"
                      autoFocus
                    />
                    <div className="text-xs text-text-muted mt-2">{draftEditContent.length} characters</div>
                  </div>
                  <div className="flex gap-2 p-4 border-t border-border">
                    <button
                      onClick={() => { draftActionMutation.mutate({ postId: editingDraftId, action: 'edit_approve', content: draftEditContent }); setEditingDraftId(null); setDraftEditContent('') }}
                      disabled={draftActionMutation.isPending || !draftEditContent.trim()}
                      className="text-xs bg-success/10 text-success hover:bg-success/20 px-4 py-2 rounded cursor-pointer disabled:opacity-50"
                    >
                      Save & Approve
                    </button>
                    <button
                      onClick={() => { setEditingDraftId(null); setDraftEditContent('') }}
                      className="text-xs bg-surface-hover text-text-muted hover:text-text px-4 py-2 rounded cursor-pointer"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Recent Posts */}
          {mktDashboard && mktDashboard.recent_posts.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">Recent Posts</h2>
              <div className="bg-surface border border-border rounded-lg overflow-x-auto">
                <table className="w-full min-w-[600px]">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left text-xs text-text-muted px-4 py-2">Platform</th>
                      <th className="text-left text-xs text-text-muted px-4 py-2">Content</th>
                      <th className="text-left text-xs text-text-muted px-4 py-2">Topic</th>
                      <th className="text-left text-xs text-text-muted px-4 py-2">Model</th>
                      <th className="text-right text-xs text-text-muted px-4 py-2">Cost</th>
                      <th className="text-left text-xs text-text-muted px-4 py-2">When</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mktDashboard.recent_posts.map((post) => (
                      <tr key={post.id} className="border-b border-border/50">
                        <td className="text-xs px-4 py-2 capitalize">{post.platform}</td>
                        <td className="text-xs px-4 py-2 max-w-[200px] truncate">{post.url ? <a href={post.url} target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300 hover:underline">{post.content}</a> : post.content}</td>
                        <td className="text-xs px-4 py-2 capitalize">{post.topic ?? '—'}</td>
                        <td className="text-xs px-4 py-2 text-text-muted">{post.llm_model ?? 'template'}</td>
                        <td className="text-xs px-4 py-2 text-right">${(post.llm_cost_usd ?? 0).toFixed(4)}</td>
                        <td className="text-xs px-4 py-2 text-text-muted">{post.posted_at ? timeAgo(post.posted_at) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Empty state */}
          {mktDashboard && mktDashboard.recent_posts.length === 0 && (!mktDrafts || mktDrafts.length === 0) && (
            <div className="text-text-muted text-center py-10">
              No marketing activity yet. Configure platform API keys and trigger a marketing tick to get started.
            </div>
          )}
        </>
      )}
    </div>
  )
}
