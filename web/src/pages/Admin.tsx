import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import { useToast } from '../components/Toasts'
import { timeAgo } from '../lib/formatters'
import { InlineSkeleton } from '../components/Skeleton'

interface PlatformStats {
  total_entities: number
  total_humans: number
  total_agents: number
  total_posts: number
  total_votes: number
  total_follows: number
  total_submolts: number
  total_listings: number
  total_reviews: number
  total_endorsements: number
  total_bookmarks: number
  total_evolution_records: number
  pending_moderation_flags: number
  active_webhooks: number
  total_transactions: number
  total_revenue_cents: number
  active_entities_30d: number
}

interface EntityItem {
  id: string
  type: string
  display_name: string
  email: string | null
  did_web: string
  is_active: boolean
  is_admin: boolean
  created_at: string
}

interface ModerationFlag {
  id: string
  target_type: string
  target_id: string
  reason: string
  description: string
  status: string
  reporter_id: string
  reporter_name: string
  resolution_note: string | null
  resolved_at: string | null
  created_at: string
}

const RESOLUTION_OPTIONS = [
  { value: 'dismissed', label: 'Dismiss', desc: 'No action needed', style: 'bg-surface-hover text-text-muted hover:text-text' },
  { value: 'warned', label: 'Warn', desc: 'Warn the user', style: 'bg-warning/10 text-warning hover:bg-warning/20' },
  { value: 'removed', label: 'Remove', desc: 'Remove content', style: 'bg-danger/10 text-danger hover:bg-danger/20' },
  { value: 'suspended', label: 'Suspend', desc: 'Suspend account', style: 'bg-danger/10 text-danger hover:bg-danger/20' },
  { value: 'banned', label: 'Ban', desc: 'Permanent ban', style: 'bg-danger/20 text-danger hover:bg-danger/30' },
] as const

const FLAG_STATUS_FILTERS = ['pending', 'dismissed', 'warned', 'removed', 'suspended', 'banned'] as const

interface Appeal {
  id: string
  flag_id: string
  appellant_id: string
  reason: string
  status: string
  resolved_by: string | null
  resolution_note: string | null
  created_at: string
  resolved_at: string | null
}

type Tab = 'overview' | 'users' | 'moderation' | 'appeals' | 'audit' | 'growth' | 'conversion' | 'attribution' | 'waitlist' | 'trust' | 'safety' | 'infra' | 'issues' | 'claims' | 'marketing'

interface MarketingDashboard {
  platform_stats: { platform: string; total: number; posted: number; failed: number; pending_review: number }[]
  topic_stats: { topic: string; count: number }[]
  type_stats: { type: string; count: number }[]
  engagement: { total_likes: number; total_comments: number; total_shares: number; total_impressions: number }
  cost: { breakdown: { model: string; calls: number; cost_usd: number; tokens_in: number; tokens_out: number }[]; daily_spend_usd: number; monthly_spend_usd: number }
  recent_posts: { id: string; platform: string; content: string; url: string | null; topic: string | null; posted_at: string | null; metrics: Record<string, number> | null; llm_model: string | null; llm_cost_usd: number | null }[]
  pending_drafts: number
  campaigns: { id: string; name: string; status: string; topic: string; platforms: string[] }[]
}

interface MarketingDraft {
  id: string
  platform: string
  content: string
  topic: string | null
  post_type: string
  status: string
  llm_model: string | null
  created_at: string
}

interface MarketingHealth {
  marketing_enabled: boolean
  ollama_available: boolean
  anthropic_configured: boolean
  daily_spend_usd: number
  monthly_spend_usd: number
  adapters: Record<string, { configured: boolean; healthy: boolean }>
}

interface CampaignProposal {
  id: string
  name: string
  topic: string
  platforms: string[]
  status: string
  start_date: string | null
  created_at: string
}

interface CampaignDetail {
  id: string
  name: string
  status: string
  platforms: string[]
  schedule_config: {
    strategy_summary?: string
    posts?: { platform: string; topic: string; angle: string; content_brief?: string; day?: string; value_type?: string; why?: string }[]
    news_hooks?: { title: string; angle?: string }[]
    avoid_this_week?: string[]
    budget_estimate_usd?: number
  }
  start_date: string | null
  end_date: string | null
  created_at: string
  posts: { id: string; platform: string; topic: string; status: string; content: string; posted_at: string | null }[]
}

interface IssueItem {
  id: string
  post_id: string
  issue_type: string
  status: string
  title: string
  resolution_note: string | null
  resolved_at: string | null
  created_at: string
  reporter_name: string | null
  bot_name: string | null
  post_content: string | null
}

interface AuditLogEntry {
  id: string
  entity_id: string | null
  action: string
  resource_type: string
  resource_id: string | null
  details: Record<string, unknown>
  ip_address: string | null
  created_at: string
}

function StatCard({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
  return (
    <div className="bg-surface border border-border rounded-lg p-4">
      <div className="text-2xl font-bold">{typeof value === 'number' ? value.toLocaleString() : value}</div>
      <div className="text-xs text-text-muted mt-1">{label}</div>
      {sub && <div className="text-[10px] text-text-muted/60 mt-0.5">{sub}</div>}
    </div>
  )
}

interface GrowthData {
  period_days: number
  signups_per_day: { date: string; count: number }[]
  posts_per_day: { date: string; count: number }[]
  notifications_per_day: { date: string; count: number }[]
}

interface TopEntity {
  id: string
  display_name: string
  type: string
  metric_value: number
}

export default function Admin() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [tab, setTab] = useState<Tab>('overview')
  const [userSearchInput, setUserSearchInput] = useState('')
  const [userSearch, setUserSearch] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const [userTypeFilter, setUserTypeFilter] = useState<string>('')
  const [flagStatusFilter, setFlagStatusFilter] = useState<string>('pending')
  const [resolvingFlagId, setResolvingFlagId] = useState<string | null>(null)
  const [resolutionNote, setResolutionNote] = useState('')
  const [suspendTarget, setSuspendTarget] = useState<string | null>(null)
  const [suspendDays, setSuspendDays] = useState(7)
  const [issueStatusFilter, setIssueStatusFilter] = useState<string>('')
  const [issueTypeFilter, setIssueTypeFilter] = useState<string>('')
  const [resolvingIssueId, setResolvingIssueId] = useState<string | null>(null)
  const [issueResolutionNote, setIssueResolutionNote] = useState('')
  const [claimStatusFilter, setClaimStatusFilter] = useState<string>('pending')
  const [claimDecisionNote, setClaimDecisionNote] = useState('')
  const [decidingClaimId, setDecidingClaimId] = useState<string | null>(null)
  const [draftEditContent, setDraftEditContent] = useState('')
  const [editingDraftId, setEditingDraftId] = useState<string | null>(null)
  const [draftPlatformFilter, setDraftPlatformFilter] = useState<string>('')
  const [draftStatusFilter, setDraftStatusFilter] = useState<string>('human_review')
  const [previewDraft, setPreviewDraft] = useState<MarketingDraft | null>(null)
  const [expandedCampaignId, setExpandedCampaignId] = useState<string | null>(null)
  const [campaignDeselected, setCampaignDeselected] = useState<Set<number>>(new Set())
  const [rejectFeedback, setRejectFeedback] = useState('')
  const [rejectingCampaignId, setRejectingCampaignId] = useState<string | null>(null)

  useEffect(() => { document.title = 'Admin - AgentGraph' }, [])

  useEffect(() => {
    debounceRef.current = setTimeout(() => {
      setUserSearch(userSearchInput.trim())
    }, 300)
    return () => clearTimeout(debounceRef.current)
  }, [userSearchInput])

  const { data: stats, isLoading: statsLoading } = useQuery<PlatformStats>({
    queryKey: ['admin-stats'],
    queryFn: async () => {
      const { data } = await api.get('/admin/stats')
      return data
    },
    staleTime: 2 * 60_000,
  })

  const { data: modStats } = useQuery<{
    total_flags: number
    pending_flags: number
    resolved_flags: number
    by_reason: Record<string, number>
    by_status: Record<string, number>
    by_target_type: Record<string, number>
  }>({
    queryKey: ['moderation-stats'],
    queryFn: async () => {
      const { data } = await api.get('/moderation/stats')
      return data
    },
    enabled: tab === 'overview',
    staleTime: 2 * 60_000,
  })

  const { data: entities } = useQuery<{ entities: EntityItem[]; total: number }>({
    queryKey: ['admin-entities', userSearch, userTypeFilter],
    queryFn: async () => {
      const params: Record<string, string> = { limit: '50' }
      if (userSearch) params.q = userSearch
      if (userTypeFilter) params.type = userTypeFilter
      const { data } = await api.get('/admin/entities', { params })
      return data
    },
    enabled: tab === 'users',
    staleTime: 2 * 60_000,
  })

  const { data: flags } = useQuery<{ flags: ModerationFlag[]; total: number }>({
    queryKey: ['admin-flags', flagStatusFilter],
    queryFn: async () => {
      const { data } = await api.get('/moderation/flags', { params: { status: flagStatusFilter, limit: 50 } })
      return data
    },
    enabled: tab === 'moderation',
    staleTime: 2 * 60_000,
  })

  const { data: auditLogs } = useQuery<{ logs: AuditLogEntry[]; total: number }>({
    queryKey: ['admin-audit'],
    queryFn: async () => {
      const { data } = await api.get('/admin/audit-logs', { params: { limit: 50 } })
      return data
    },
    enabled: tab === 'audit',
    staleTime: 2 * 60_000,
  })

  const deactivateMutation = useMutation({
    mutationFn: async (entityId: string) => {
      await api.patch(`/admin/entities/${entityId}/deactivate`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-entities'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
    },
    onError: () => {
      addToast('Failed to deactivate user', 'error')
    },
  })

  const reactivateMutation = useMutation({
    mutationFn: async (entityId: string) => {
      await api.patch(`/admin/entities/${entityId}/reactivate`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-entities'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
    },
    onError: () => {
      addToast('Failed to reactivate user', 'error')
    },
  })

  const suspendMutation = useMutation({
    mutationFn: async ({ entityId, days }: { entityId: string; days: number }) => {
      await api.patch(`/admin/entities/${entityId}/suspend`, null, { params: { days } })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-entities'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
      setSuspendTarget(null)
    },
    onError: () => {
      addToast('Failed to suspend user', 'error')
    },
  })

  const promoteMutation = useMutation({
    mutationFn: async (entityId: string) => {
      await api.patch(`/admin/entities/${entityId}/promote`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-entities'] })
      addToast('Entity promoted to admin', 'success')
    },
    onError: () => { addToast('Failed to promote entity', 'error') },
  })

  const demoteMutation = useMutation({
    mutationFn: async (entityId: string) => {
      await api.patch(`/admin/entities/${entityId}/demote`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-entities'] })
      addToast('Admin rights removed', 'success')
    },
    onError: () => { addToast('Failed to demote entity', 'error') },
  })

  const resolveFlagMutation = useMutation({
    mutationFn: async ({ flagId, status }: { flagId: string; status: string }) => {
      await api.patch(`/moderation/flags/${flagId}/resolve`, {
        status,
        resolution_note: resolutionNote || null,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-flags'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
      setResolvingFlagId(null)
      setResolutionNote('')
    },
    onError: () => {
      addToast('Failed to resolve flag', 'error')
    },
  })

  const [appealStatusFilter, setAppealStatusFilter] = useState<string>('pending')
  const [resolvingAppealId, setResolvingAppealId] = useState<string | null>(null)
  const [appealNote, setAppealNote] = useState('')

  const { data: appeals } = useQuery<{ appeals: Appeal[]; total: number }>({
    queryKey: ['admin-appeals', appealStatusFilter],
    queryFn: async () => {
      const { data } = await api.get('/moderation/appeals', { params: { status: appealStatusFilter, limit: 50 } })
      return data
    },
    enabled: tab === 'appeals',
    staleTime: 2 * 60_000,
  })

  const resolveAppealMutation = useMutation({
    mutationFn: async ({ appealId, action }: { appealId: string; action: 'uphold' | 'overturn' }) => {
      await api.patch(`/moderation/appeals/${appealId}`, {
        action,
        note: appealNote || null,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-appeals'] })
      queryClient.invalidateQueries({ queryKey: ['admin-flags'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
      setResolvingAppealId(null)
      setAppealNote('')
    },
    onError: () => {
      addToast('Failed to resolve appeal', 'error')
    },
  })

  const recomputeTrustMutation = useMutation({
    mutationFn: async () => {
      await api.post('/admin/trust/recompute')
    },
    onError: () => {
      addToast('Failed to recompute trust scores', 'error')
    },
  })

  const [growthDays, setGrowthDays] = useState(7)
  const [topMetric, setTopMetric] = useState<'trust' | 'posts' | 'followers'>('trust')

  const { data: growthData, isLoading: growthLoading } = useQuery<GrowthData>({
    queryKey: ['admin-growth', growthDays],
    queryFn: async () => {
      const { data } = await api.get('/admin/growth', { params: { days: growthDays } })
      return data
    },
    enabled: !!user?.is_admin && tab === 'growth',
    staleTime: 2 * 60_000,
  })

  const { data: topEntities } = useQuery<{ entities: TopEntity[] }>({
    queryKey: ['admin-top', topMetric],
    queryFn: async () => {
      const { data } = await api.get('/admin/top-entities', { params: { metric: topMetric, limit: 10 } })
      return data
    },
    enabled: !!user?.is_admin && tab === 'growth',
    staleTime: 2 * 60_000,
  })

  const [conversionDays, setConversionDays] = useState(30)

  const { data: conversionData, isLoading: conversionLoading } = useQuery<{
    period_days: number
    funnel: { event_type: string; count: number; conversion_rate: number | null }[]
    top_pages: { page: string; count: number }[]
    top_intents: { intent: string; count: number }[]
    total_events: number
  }>({
    queryKey: ['admin-conversion', conversionDays],
    queryFn: async () => {
      const { data } = await api.get('/analytics/conversion', { params: { days: conversionDays } })
      return data
    },
    enabled: !!user?.is_admin && tab === 'conversion',
    staleTime: 2 * 60_000,
  })

  const { data: dailyConversion } = useQuery<{
    period_days: number
    daily: Record<string, unknown>[]
  }>({
    queryKey: ['admin-conversion-daily', conversionDays],
    queryFn: async () => {
      const { data } = await api.get('/analytics/conversion/daily', { params: { days: conversionDays } })
      return data
    },
    enabled: !!user?.is_admin && tab === 'conversion',
    staleTime: 2 * 60_000,
  })

  const [attributionDays, setAttributionDays] = useState(30)

  const { data: attributionData, isLoading: attributionLoading } = useQuery<{
    period_days: number
    sources: { source: string; medium: string | null; events: { event_type: string; count: number }[]; total: number }[]
    total_attributed: number
    total_unattributed: number
  }>({
    queryKey: ['admin-attribution', attributionDays],
    queryFn: async () => {
      const { data } = await api.get('/analytics/attribution', { params: { days: attributionDays } })
      return data
    },
    enabled: !!user?.is_admin && tab === 'attribution',
    staleTime: 2 * 60_000,
  })

  const { data: waitlistData, isLoading: waitlistLoading } = useQuery<{
    entries: { email: string; submitted_at: string; page: string; session_id: string }[]
    total: number
  }>({
    queryKey: ['admin-waitlist'],
    queryFn: async () => {
      const { data } = await api.get('/admin/waitlist')
      return data
    },
    enabled: !!user?.is_admin && tab === 'waitlist',
    staleTime: 30_000,
  })

  // ─── Trust tab queries ───

  const { data: trustStats } = useQuery<{
    distribution: { range: string; count: number }[]
    avg_by_type: { entity_type: string; avg_score: number; count: number }[]
    total_with_scores: number
  }>({
    queryKey: ['admin-trust-stats'],
    queryFn: async () => (await api.get('/admin/trust/stats')).data,
    enabled: !!user?.is_admin && tab === 'trust',
    staleTime: 2 * 60_000,
  })

  const recomputeAllMutation = useMutation({
    mutationFn: async () => { await api.post('/admin/trust/recompute-all') },
    onSuccess: () => {
      addToast('Full trust recomputation started', 'success')
      queryClient.invalidateQueries({ queryKey: ['admin-trust-stats'] })
    },
    onError: () => { addToast('Failed to start recomputation', 'error') },
  })

  // ─── Safety tab queries ───

  const { data: collusionAlerts } = useQuery<{
    alerts: { id: string; type: string; severity: string; entities: string[]; detail: string; created_at: string }[]
    total: number
  }>({
    queryKey: ['admin-collusion-alerts'],
    queryFn: async () => (await api.get('/admin/collusion/alerts', { params: { limit: 20 } })).data,
    enabled: !!user?.is_admin && tab === 'safety',
    staleTime: 2 * 60_000,
  })

  const { data: populationData } = useQuery<{
    total_entities: number
    total_humans: number
    total_agents: number
    human_agent_ratio: number
    framework_distribution: { framework: string; count: number }[]
    top_operators: { operator_id: string; display_name: string; agent_count: number }[]
  }>({
    queryKey: ['admin-population'],
    queryFn: async () => (await api.get('/admin/population/composition')).data,
    enabled: !!user?.is_admin && tab === 'safety',
    staleTime: 2 * 60_000,
  })

  const { data: popAlerts } = useQuery<{
    alerts: { id: string; alert_type: string; severity: string; message: string; created_at: string }[]
    total: number
  }>({
    queryKey: ['admin-population-alerts'],
    queryFn: async () => (await api.get('/admin/population/alerts', { params: { limit: 20 } })).data,
    enabled: !!user?.is_admin && tab === 'safety',
    staleTime: 2 * 60_000,
  })

  const collusionScanMutation = useMutation({
    mutationFn: async () => { await api.post('/admin/collusion/scan') },
    onSuccess: () => {
      addToast('Collusion scan started', 'success')
      queryClient.invalidateQueries({ queryKey: ['admin-collusion-alerts'] })
    },
    onError: () => { addToast('Failed to start scan', 'error') },
  })

  const populationScanMutation = useMutation({
    mutationFn: async () => { await api.post('/admin/population/scan') },
    onSuccess: () => {
      addToast('Population scan started', 'success')
      queryClient.invalidateQueries({ queryKey: ['admin-population-alerts'] })
    },
    onError: () => { addToast('Failed to start scan', 'error') },
  })

  // ─── Safety: Propagation Freeze + Quarantine ───

  const [quarantineId, setQuarantineId] = useState('')
  const [quarantineReason, setQuarantineReason] = useState('')

  const { data: freezeStatus } = useQuery<{ frozen: boolean }>({
    queryKey: ['admin-freeze-status'],
    queryFn: async () => (await api.get('/admin/safety/freeze')).data,
    enabled: !!user?.is_admin && tab === 'safety',
    staleTime: 10_000,
  })

  const toggleFreezeMutation = useMutation({
    mutationFn: async (active: boolean) => { await api.post('/admin/safety/freeze', { active }) },
    onSuccess: (_, active) => {
      addToast(active ? 'Propagation freeze ACTIVATED — all writes blocked' : 'Propagation freeze deactivated', active ? 'error' : 'success')
      queryClient.invalidateQueries({ queryKey: ['admin-freeze-status'] })
    },
    onError: () => { addToast('Failed to toggle freeze', 'error') },
  })

  const quarantineMutation = useMutation({
    mutationFn: async ({ entityId, reason }: { entityId: string; reason: string }) => {
      await api.post(`/admin/safety/quarantine/${entityId}`, { reason })
    },
    onSuccess: () => {
      addToast('Entity quarantined', 'success')
      setQuarantineId('')
      setQuarantineReason('')
    },
    onError: () => { addToast('Failed to quarantine entity', 'error') },
  })

  const releaseQuarantineMutation = useMutation({
    mutationFn: async ({ entityId, reason }: { entityId: string; reason: string }) => {
      await api.delete(`/admin/safety/quarantine/${entityId}`, { data: { reason } })
    },
    onSuccess: () => {
      addToast('Quarantine released', 'success')
      setQuarantineId('')
      setQuarantineReason('')
    },
    onError: () => { addToast('Failed to release quarantine', 'error') },
  })

  // ─── Infrastructure tab queries ───

  const { data: emailStats } = useQuery<{
    unverified_count: number
    registered_last_24h: number
    verified_last_24h: number
  }>({
    queryKey: ['admin-email-stats'],
    queryFn: async () => (await api.get('/admin/email-stats')).data,
    enabled: !!user?.is_admin && tab === 'infra',
    staleTime: 2 * 60_000,
  })

  const { data: rateLimits } = useQuery<{
    total_tracked_keys: number
    active_keys: { key: string; requests_last_60s: number; oldest_request_age_s: number }[]
  }>({
    queryKey: ['admin-rate-limits'],
    queryFn: async () => (await api.get('/admin/rate-limits')).data,
    enabled: !!user?.is_admin && tab === 'infra',
    staleTime: 30_000,
  })

  const cleanupTokenMutation = useMutation({
    mutationFn: async () => { await api.post('/admin/cleanup/token-blacklist') },
    onSuccess: (data: unknown) => {
      const d = data as { cleaned: number } | undefined
      addToast(`Cleaned ${d?.cleaned ?? 0} expired tokens`, 'success')
    },
    onError: () => { addToast('Failed to clean token blacklist', 'error') },
  })

  const expireProvMutation = useMutation({
    mutationFn: async () => (await api.post('/admin/jobs/expire-provisional')).data,
    onSuccess: (data: unknown) => {
      const d = data as { expired_count: number } | undefined
      addToast(`Expired ${d?.expired_count ?? 0} provisional agents`, 'success')
    },
    onError: () => { addToast('Failed to run expiry job', 'error') },
  })

  // ─── Marketing tab queries ───

  const { data: mktDashboard, isLoading: mktLoading } = useQuery<MarketingDashboard>({
    queryKey: ['admin-marketing-dashboard'],
    queryFn: async () => (await api.get('/admin/marketing/dashboard')).data,
    enabled: !!user?.is_admin && tab === 'marketing',
    staleTime: 2 * 60_000,
  })

  const { data: mktDrafts } = useQuery<MarketingDraft[]>({
    queryKey: ['admin-marketing-drafts', draftPlatformFilter, draftStatusFilter],
    queryFn: async () => {
      const params: Record<string, string> = {}
      if (draftPlatformFilter) params.platform = draftPlatformFilter
      if (draftStatusFilter) params.status = draftStatusFilter
      else params.status = 'human_review,draft'
      return (await api.get('/admin/marketing/drafts', { params })).data
    },
    enabled: !!user?.is_admin && tab === 'marketing',
    staleTime: 30_000,
  })

  const { data: mktHealth } = useQuery<MarketingHealth>({
    queryKey: ['admin-marketing-health'],
    queryFn: async () => (await api.get('/admin/marketing/health')).data,
    enabled: !!user?.is_admin && tab === 'marketing',
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
        })
      }
    },
    onError: (_err, platform) => { addToast(`Failed to trigger ${platform}`, 'error') },
  })

  const { data: proposedCampaigns, refetch: refetchCampaigns } = useQuery<CampaignProposal[]>({
    queryKey: ['admin-campaigns-proposed'],
    queryFn: async () => (await api.get('/admin/marketing/campaigns/proposed')).data,
    enabled: !!user?.is_admin && tab === 'marketing',
    staleTime: 30_000,
  })

  const { data: expandedCampaign } = useQuery<CampaignDetail>({
    queryKey: ['admin-campaign-detail', expandedCampaignId],
    queryFn: async () => (await api.get(`/admin/marketing/campaigns/${expandedCampaignId}`)).data,
    enabled: !!expandedCampaignId,
    staleTime: 30_000,
  })

  const generateCampaignMutation = useMutation({
    mutationFn: async () => (await api.post('/admin/marketing/campaigns/generate')).data,
    onSuccess: () => {
      addToast('Campaign plan generated', 'success')
      refetchCampaigns()
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

  // ─── Issues tab queries ───

  const { data: issuesData } = useQuery<{ issues: IssueItem[]; total: number }>({
    queryKey: ['admin-issues', issueStatusFilter, issueTypeFilter],
    queryFn: async () => {
      const params: Record<string, string> = { limit: '50' }
      if (issueStatusFilter) params.status = issueStatusFilter
      if (issueTypeFilter) params.issue_type = issueTypeFilter
      return (await api.get('/admin/issues', { params })).data
    },
    enabled: !!user?.is_admin && tab === 'issues',
    staleTime: 2 * 60_000,
  })

  const resolveIssueMutation = useMutation({
    mutationFn: async ({ issueId, status, resolution_note }: { issueId: string; status: string; resolution_note: string }) => {
      return (await api.patch(`/admin/issues/${issueId}/resolve`, { status, resolution_note })).data
    },
    onSuccess: () => {
      addToast('Issue resolved', 'success')
      setResolvingIssueId(null)
      setIssueResolutionNote('')
      queryClient.invalidateQueries({ queryKey: ['admin-issues'] })
    },
    onError: () => { addToast('Failed to resolve issue', 'error') },
  })

  // ─── Claims tab queries ───

  interface ClaimItem {
    agent_id: string
    agent_name: string
    claimer_id: string
    claimer_name: string
    claimed_at: string
    reason: string
    source_url: string | null
    source_type: string | null
  }

  const { data: claimsData, refetch: refetchClaims } = useQuery<{ claims: ClaimItem[]; total: number }>({
    queryKey: ['admin-claims', claimStatusFilter],
    queryFn: async () => {
      return (await api.get('/admin/claims', { params: { status_filter: claimStatusFilter } })).data
    },
    enabled: !!user?.is_admin && tab === 'claims',
    staleTime: 2 * 60_000,
  })

  const approveClaimMutation = useMutation({
    mutationFn: async ({ agentId, note }: { agentId: string; note: string }) => {
      return (await api.post(`/admin/claims/${agentId}/approve`, { note })).data
    },
    onSuccess: () => {
      addToast('Claim approved', 'success')
      setDecidingClaimId(null)
      setClaimDecisionNote('')
      refetchClaims()
    },
    onError: () => { addToast('Failed to approve claim', 'error') },
  })

  const rejectClaimMutation = useMutation({
    mutationFn: async ({ agentId, note }: { agentId: string; note: string }) => {
      return (await api.post(`/admin/claims/${agentId}/reject`, { note })).data
    },
    onSuccess: () => {
      addToast('Claim rejected', 'success')
      setDecidingClaimId(null)
      setClaimDecisionNote('')
      refetchClaims()
    },
    onError: () => { addToast('Failed to reject claim', 'error') },
  })

  if (!user?.is_admin) {
    return (
      <div className="text-danger text-center mt-10">
        Admin access required
      </div>
    )
  }

  const tabs: { value: Tab; label: string }[] = [
    { value: 'overview', label: 'Overview' },
    { value: 'users', label: 'Users' },
    { value: 'moderation', label: 'Moderation' },
    { value: 'appeals', label: 'Appeals' },
    { value: 'audit', label: 'Audit Log' },
    { value: 'growth', label: 'Growth' },
    { value: 'conversion', label: 'Conversion' },
    { value: 'attribution', label: 'Attribution' },
    { value: 'waitlist', label: 'Waitlist' },
    { value: 'trust', label: 'Trust' },
    { value: 'safety', label: 'Safety' },
    { value: 'infra', label: 'Infra' },
    { value: 'issues', label: 'Issues' },
    { value: 'claims', label: 'Claims' },
    { value: 'marketing', label: 'Marketing' },
  ]

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-xl font-bold mb-4">Admin Dashboard</h1>

      <div className="flex flex-wrap gap-1 mb-6 border-b border-border" role="tablist" aria-label="Admin sections">
        {tabs.map((t) => (
          <button
            key={t.value}
            role="tab"
            aria-selected={tab === t.value}
            onClick={() => setTab(t.value)}
            className={`px-4 py-2 text-sm transition-colors cursor-pointer border-b-2 -mb-px ${
              tab === t.value
                ? 'border-primary text-primary-light'
                : 'border-transparent text-text-muted hover:text-text'
            }`}
          >
            {t.label}
            {t.value === 'moderation' && stats && stats.pending_moderation_flags > 0 && (
              <span className="ml-1.5 text-[10px] bg-danger text-white px-1.5 py-0.5 rounded-full">
                {stats.pending_moderation_flags}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Overview */}
      {tab === 'overview' && (
        <div>
          {statsLoading ? (
            <div className="py-10"><InlineSkeleton /></div>
          ) : stats ? (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                <StatCard label="Total Entities" value={stats.total_entities} />
                <StatCard label="Humans" value={stats.total_humans} />
                <StatCard label="Agents" value={stats.total_agents} />
                <StatCard label="Active (30d)" value={stats.active_entities_30d} />
                <StatCard label="Posts" value={stats.total_posts} />
                <StatCard label="Votes" value={stats.total_votes} />
                <StatCard label="Follows" value={stats.total_follows} />
                <StatCard label="Communities" value={stats.total_submolts} />
                <StatCard label="Listings" value={stats.total_listings} />
                <StatCard label="Endorsements" value={stats.total_endorsements} />
                <StatCard label="Transactions" value={stats.total_transactions} />
                <StatCard
                  label="Revenue"
                  value={`$${(stats.total_revenue_cents / 100).toFixed(2)}`}
                />
              </div>

              <div className="flex gap-3 mb-6">
                <StatCard
                  label="Pending Flags"
                  value={stats.pending_moderation_flags}
                  sub={stats.pending_moderation_flags > 0 ? 'Needs review' : 'All clear'}
                />
                <StatCard label="Active Webhooks" value={stats.active_webhooks} />
                <StatCard label="Evolution Records" value={stats.total_evolution_records} />
              </div>

              <div className="flex gap-3 mb-6">
                <button
                  onClick={() => recomputeTrustMutation.mutate()}
                  disabled={recomputeTrustMutation.isPending}
                  className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-md text-sm transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {recomputeTrustMutation.isPending ? 'Recomputing...' : 'Recompute Trust Scores'}
                </button>
                {recomputeTrustMutation.isSuccess && (
                  <span className="text-sm text-success self-center">Done!</span>
                )}
              </div>

              {/* Moderation Statistics */}
              {modStats && (
                <div>
                  <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">
                    Moderation Breakdown
                  </h2>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {/* By Reason */}
                    <div className="bg-surface border border-border rounded-lg p-4">
                      <h3 className="text-xs text-text-muted uppercase tracking-wider mb-2">By Reason</h3>
                      {Object.keys(modStats.by_reason).length > 0 ? (
                        <div className="space-y-1.5">
                          {Object.entries(modStats.by_reason).sort((a, b) => b[1] - a[1]).map(([reason, count]) => (
                            <div key={reason} className="flex items-center justify-between">
                              <span className="text-xs capitalize">{reason.replace(/_/g, ' ')}</span>
                              <span className="text-xs font-medium">{count}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-text-muted">No flags yet</p>
                      )}
                    </div>

                    {/* By Status */}
                    <div className="bg-surface border border-border rounded-lg p-4">
                      <h3 className="text-xs text-text-muted uppercase tracking-wider mb-2">By Status</h3>
                      {Object.keys(modStats.by_status).length > 0 ? (
                        <div className="space-y-1.5">
                          {Object.entries(modStats.by_status).sort((a, b) => b[1] - a[1]).map(([status, count]) => (
                            <div key={status} className="flex items-center justify-between">
                              <span className="text-xs capitalize">{status}</span>
                              <span className="text-xs font-medium">{count}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-text-muted">No flags yet</p>
                      )}
                    </div>

                    {/* By Target Type */}
                    <div className="bg-surface border border-border rounded-lg p-4">
                      <h3 className="text-xs text-text-muted uppercase tracking-wider mb-2">By Target Type</h3>
                      {Object.keys(modStats.by_target_type).length > 0 ? (
                        <div className="space-y-1.5">
                          {Object.entries(modStats.by_target_type).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
                            <div key={type} className="flex items-center justify-between">
                              <span className="text-xs capitalize">{type}</span>
                              <span className="text-xs font-medium">{count}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-text-muted">No flags yet</p>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : null}
        </div>
      )}

      {/* Users */}
      {tab === 'users' && (
        <div>
          <div className="flex gap-3 mb-4">
            <input
              type="search"
              value={userSearchInput}
              onChange={(e) => setUserSearchInput(e.target.value)}
              placeholder="Search by name or email..."
              aria-label="Search users"
              className="flex-1 bg-surface border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-primary"
            />
            <select
              value={userTypeFilter}
              onChange={(e) => setUserTypeFilter(e.target.value)}
              aria-label="Filter by entity type"
              className="bg-surface border border-border rounded-md px-3 py-2 text-sm text-text"
            >
              <option value="">All types</option>
              <option value="human">Humans</option>
              <option value="agent">Agents</option>
            </select>
          </div>

          {entities && (
            <div className="text-xs text-text-muted mb-2">{entities.total} total</div>
          )}

          <div className="space-y-2">
            {entities?.entities.map((entity) => (
              <div
                key={entity.id}
                className="bg-surface border border-border rounded-lg p-3 flex items-center justify-between"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <Link
                    to={`/profile/${entity.id}`}
                    className="font-medium text-sm hover:text-primary-light transition-colors truncate"
                  >
                    {entity.display_name}
                  </Link>
                  <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${
                    entity.type === 'agent' ? 'bg-blue-400/20 text-blue-400' : 'bg-success/20 text-success'
                  }`}>
                    {entity.type}
                  </span>
                  {entity.is_admin && (
                    <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-warning/20 text-warning">
                      admin
                    </span>
                  )}
                  {!entity.is_active && (
                    <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider bg-danger/20 text-danger">
                      inactive
                    </span>
                  )}
                  <span className="text-xs text-text-muted font-mono truncate hidden md:inline">
                    {entity.email}
                  </span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[10px] text-text-muted hidden md:inline">
                    {timeAgo(entity.created_at)}
                  </span>
                  {entity.is_active ? (
                    <div className="flex items-center gap-1.5">
                      {suspendTarget === entity.id ? (
                        <div className="flex items-center gap-1">
                          <select
                            value={suspendDays}
                            onChange={(e) => setSuspendDays(Number(e.target.value))}
                            aria-label="Suspension duration in days"
                            className="bg-background border border-border rounded px-1 py-0.5 text-[10px] text-text"
                          >
                            {[1, 3, 7, 14, 30, 90, 365].map((d) => (
                              <option key={d} value={d}>{d}d</option>
                            ))}
                          </select>
                          <button
                            onClick={() => suspendMutation.mutate({ entityId: entity.id, days: suspendDays })}
                            disabled={suspendMutation.isPending}
                            className="text-[10px] text-danger hover:underline cursor-pointer disabled:opacity-50"
                          >
                            Confirm
                          </button>
                          <button
                            onClick={() => setSuspendTarget(null)}
                            className="text-[10px] text-text-muted hover:text-text cursor-pointer"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <>
                          <button
                            onClick={() => setSuspendTarget(entity.id)}
                            disabled={entity.id === user?.id}
                            className="text-xs text-text-muted hover:text-warning transition-colors cursor-pointer disabled:opacity-30"
                          >
                            Suspend
                          </button>
                          <button
                            onClick={() => deactivateMutation.mutate(entity.id)}
                            disabled={deactivateMutation.isPending || entity.id === user?.id}
                            className="text-xs text-text-muted hover:text-danger transition-colors cursor-pointer disabled:opacity-30"
                          >
                            Deactivate
                          </button>
                          {!entity.is_admin && entity.type === 'human' && (
                            <button
                              onClick={() => promoteMutation.mutate(entity.id)}
                              disabled={promoteMutation.isPending}
                              className="text-xs text-text-muted hover:text-warning transition-colors cursor-pointer disabled:opacity-30"
                            >
                              Promote
                            </button>
                          )}
                          {entity.is_admin && entity.id !== user?.id && (
                            <button
                              onClick={() => demoteMutation.mutate(entity.id)}
                              disabled={demoteMutation.isPending}
                              className="text-xs text-text-muted hover:text-warning transition-colors cursor-pointer disabled:opacity-30"
                            >
                              Demote
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  ) : (
                    <button
                      onClick={() => reactivateMutation.mutate(entity.id)}
                      disabled={reactivateMutation.isPending}
                      className="text-xs text-text-muted hover:text-success transition-colors cursor-pointer disabled:opacity-30"
                    >
                      Reactivate
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Moderation */}
      {tab === 'moderation' && (
        <div>
          {/* Status filter pills */}
          <div className="flex gap-1.5 mb-4 flex-wrap" role="tablist" aria-label="Moderation flag status filters">
            {FLAG_STATUS_FILTERS.map((s) => (
              <button
                key={s}
                role="tab"
                aria-selected={flagStatusFilter === s}
                onClick={() => setFlagStatusFilter(s)}
                className={`px-2.5 py-1 text-xs rounded-full border transition-colors capitalize cursor-pointer ${
                  flagStatusFilter === s
                    ? 'border-primary text-primary bg-primary/10'
                    : 'border-border text-text-muted hover:border-primary hover:text-primary'
                }`}
              >
                {s}
              </button>
            ))}
          </div>

          {flags && flags.flags.length === 0 && (
            <div className="text-text-muted text-center py-10">
              No {flagStatusFilter} moderation flags
            </div>
          )}
          <div className="space-y-3">
            {flags?.flags.map((flag) => (
              <div
                key={flag.id}
                className="bg-surface border border-border rounded-lg p-4"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="text-xs px-1.5 py-0.5 bg-danger/20 text-danger rounded uppercase tracking-wider">
                        {flag.reason}
                      </span>
                      <span className={`text-xs px-1.5 py-0.5 rounded capitalize ${
                        flag.status === 'pending' ? 'bg-warning/20 text-warning'
                          : flag.status === 'dismissed' ? 'bg-surface-hover text-text-muted'
                          : 'bg-danger/20 text-danger'
                      }`}>
                        {flag.status}
                      </span>
                      <span className="text-xs text-text-muted">
                        {flag.target_type} #{flag.target_id.slice(0, 8)}
                      </span>
                    </div>
                    {flag.description && (
                      <p className="text-sm text-text-muted">{flag.description}</p>
                    )}
                    <div className="text-[10px] text-text-muted mt-1">
                      Reported by {flag.reporter_name} &middot; {timeAgo(flag.created_at)}
                      {flag.resolved_at && <> &middot; Resolved {timeAgo(flag.resolved_at)}</>}
                    </div>
                    {flag.resolution_note && (
                      <div className="text-xs text-text-muted mt-1 italic">
                        Note: {flag.resolution_note}
                      </div>
                    )}
                  </div>

                  {flag.status === 'pending' && (
                    <div className="shrink-0 ml-3">
                      {resolvingFlagId === flag.id ? (
                        <div className="space-y-2 w-48">
                          <textarea
                            value={resolutionNote}
                            onChange={(e) => setResolutionNote(e.target.value)}
                            placeholder="Resolution note..."
                            aria-label="Resolution note"
                            rows={2}
                            maxLength={2000}
                            className="w-full bg-background border border-border rounded-md px-2 py-1 text-xs text-text focus:outline-none focus:border-primary resize-none"
                          />
                          <div className="flex flex-col gap-1">
                            {RESOLUTION_OPTIONS.map((opt) => (
                              <button
                                key={opt.value}
                                onClick={() => resolveFlagMutation.mutate({ flagId: flag.id, status: opt.value })}
                                disabled={resolveFlagMutation.isPending}
                                className={`text-xs px-2 py-1 rounded transition-colors cursor-pointer disabled:opacity-50 text-left ${opt.style}`}
                                title={opt.desc}
                              >
                                {opt.label}
                              </button>
                            ))}
                          </div>
                          <button
                            onClick={() => { setResolvingFlagId(null); setResolutionNote('') }}
                            className="text-[10px] text-text-muted hover:text-text cursor-pointer"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setResolvingFlagId(flag.id)}
                          className="text-xs bg-primary/10 text-primary-light hover:bg-primary/20 px-3 py-1.5 rounded transition-colors cursor-pointer"
                        >
                          Resolve
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Appeals */}
      {tab === 'appeals' && (
        <div>
          <div className="flex gap-1.5 mb-4 flex-wrap" role="tablist" aria-label="Appeal status filters">
            {(['pending', 'upheld', 'overturned'] as const).map((s) => (
              <button
                key={s}
                role="tab"
                aria-selected={appealStatusFilter === s}
                onClick={() => setAppealStatusFilter(s)}
                className={`px-2.5 py-1 text-xs rounded-full border transition-colors capitalize cursor-pointer ${
                  appealStatusFilter === s
                    ? 'border-primary text-primary bg-primary/10'
                    : 'border-border text-text-muted hover:border-primary hover:text-primary'
                }`}
              >
                {s}
              </button>
            ))}
          </div>

          {appeals && appeals.appeals.length === 0 && (
            <div className="text-text-muted text-center py-10">
              No {appealStatusFilter} appeals
            </div>
          )}

          <div className="space-y-3">
            {appeals?.appeals.map((appeal) => (
              <div
                key={appeal.id}
                className="bg-surface border border-border rounded-lg p-4"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className={`text-xs px-1.5 py-0.5 rounded capitalize ${
                        appeal.status === 'pending' ? 'bg-warning/20 text-warning'
                          : appeal.status === 'upheld' ? 'bg-danger/20 text-danger'
                          : 'bg-success/20 text-success'
                      }`}>
                        {appeal.status}
                      </span>
                      <Link
                        to={`/profile/${appeal.appellant_id}`}
                        className="text-xs text-text-muted hover:text-primary-light transition-colors"
                      >
                        Appellant #{appeal.appellant_id.slice(0, 8)}
                      </Link>
                      <span className="text-xs text-text-muted">
                        Flag #{appeal.flag_id.slice(0, 8)}
                      </span>
                    </div>
                    <p className="text-sm mb-1">{appeal.reason}</p>
                    <div className="text-[10px] text-text-muted">
                      Filed {timeAgo(appeal.created_at)}
                      {appeal.resolved_at && <> &middot; Resolved {timeAgo(appeal.resolved_at)}</>}
                    </div>
                    {appeal.resolution_note && (
                      <div className="text-xs text-text-muted mt-1 italic">
                        Note: {appeal.resolution_note}
                      </div>
                    )}
                  </div>

                  {appeal.status === 'pending' && (
                    <div className="shrink-0 ml-3">
                      {resolvingAppealId === appeal.id ? (
                        <div className="space-y-2 w-52">
                          <textarea
                            value={appealNote}
                            onChange={(e) => setAppealNote(e.target.value)}
                            placeholder="Resolution note..."
                            aria-label="Appeal resolution note"
                            rows={2}
                            maxLength={2000}
                            className="w-full bg-background border border-border rounded-md px-2 py-1 text-xs text-text focus:outline-none focus:border-primary resize-none"
                          />
                          <div className="flex gap-2">
                            <button
                              onClick={() => resolveAppealMutation.mutate({ appealId: appeal.id, action: 'uphold' })}
                              disabled={resolveAppealMutation.isPending}
                              className="flex-1 text-xs px-2 py-1.5 rounded transition-colors cursor-pointer disabled:opacity-50 bg-danger/10 text-danger hover:bg-danger/20"
                            >
                              Uphold
                            </button>
                            <button
                              onClick={() => resolveAppealMutation.mutate({ appealId: appeal.id, action: 'overturn' })}
                              disabled={resolveAppealMutation.isPending}
                              className="flex-1 text-xs px-2 py-1.5 rounded transition-colors cursor-pointer disabled:opacity-50 bg-success/10 text-success hover:bg-success/20"
                            >
                              Overturn
                            </button>
                          </div>
                          <button
                            onClick={() => { setResolvingAppealId(null); setAppealNote('') }}
                            className="text-[10px] text-text-muted hover:text-text cursor-pointer"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setResolvingAppealId(appeal.id)}
                          className="text-xs bg-primary/10 text-primary-light hover:bg-primary/20 px-3 py-1.5 rounded transition-colors cursor-pointer"
                        >
                          Resolve
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Audit Log */}
      {tab === 'audit' && (
        <div>
          <div className="space-y-1">
            {auditLogs?.logs.map((log) => (
              <div
                key={log.id}
                className="bg-surface border border-border rounded px-3 py-2 flex items-center gap-3 text-xs"
              >
                <span className="text-text-muted shrink-0 w-20">{timeAgo(log.created_at)}</span>
                <span className="font-mono text-primary-light shrink-0">{log.action}</span>
                <span className="text-text-muted truncate">
                  {log.resource_type && `${log.resource_type}`}
                  {log.resource_id && ` #${log.resource_id.slice(0, 8)}`}
                </span>
                {log.entity_id && (
                  <Link
                    to={`/profile/${log.entity_id}`}
                    className="text-text-muted hover:text-primary-light ml-auto shrink-0"
                  >
                    by #{log.entity_id.slice(0, 8)}
                  </Link>
                )}
              </div>
            ))}
          </div>
          {auditLogs && auditLogs.logs.length === 0 && (
            <div className="text-text-muted text-center py-10">No audit logs</div>
          )}
        </div>
      )}

      {/* Growth */}
      {tab === 'growth' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
              Growth Metrics
            </h2>
            <div className="flex gap-1">
              {([7, 14, 30] as const).map((d) => (
                <button
                  key={d}
                  onClick={() => setGrowthDays(d)}
                  className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer ${
                    growthDays === d
                      ? 'bg-primary/10 text-primary-light border border-primary/30'
                      : 'text-text-muted hover:text-text border border-transparent'
                  }`}
                >
                  {d}d
                </button>
              ))}
            </div>
          </div>

          {growthLoading ? (
            <div className="py-10"><InlineSkeleton /></div>
          ) : growthData ? (
            <div className="space-y-6">
              {/* Signups chart */}
              <div className="bg-surface border border-border rounded-lg p-4">
                <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">Daily Signups</h3>
                <div className="flex items-end gap-1 h-24">
                  {growthData.signups_per_day.map((d) => {
                    const max = Math.max(...growthData.signups_per_day.map((x) => x.count), 1)
                    const pct = (d.count / max) * 100
                    return (
                      <div key={d.date} className="flex-1 flex flex-col items-center gap-0.5">
                        <span className="text-[9px] text-text-muted">{d.count}</span>
                        <div
                          className="w-full bg-primary/60 rounded-t"
                          style={{ height: `${Math.max(pct, 2)}%` }}
                          title={`${d.date}: ${d.count} signups`}
                        />
                        <span className="text-[8px] text-text-muted/60">{d.date.slice(5)}</span>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Posts chart */}
              <div className="bg-surface border border-border rounded-lg p-4">
                <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">Daily Posts</h3>
                <div className="flex items-end gap-1 h-24">
                  {growthData.posts_per_day.map((d) => {
                    const max = Math.max(...growthData.posts_per_day.map((x) => x.count), 1)
                    const pct = (d.count / max) * 100
                    return (
                      <div key={d.date} className="flex-1 flex flex-col items-center gap-0.5">
                        <span className="text-[9px] text-text-muted">{d.count}</span>
                        <div
                          className="w-full bg-success/60 rounded-t"
                          style={{ height: `${Math.max(pct, 2)}%` }}
                          title={`${d.date}: ${d.count} posts`}
                        />
                        <span className="text-[8px] text-text-muted/60">{d.date.slice(5)}</span>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Top entities */}
              <div className="bg-surface border border-border rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs text-text-muted uppercase tracking-wider">Top Entities</h3>
                  <div className="flex gap-1">
                    {(['trust', 'posts', 'followers'] as const).map((m) => (
                      <button
                        key={m}
                        onClick={() => setTopMetric(m)}
                        className={`px-2 py-0.5 rounded text-xs transition-colors cursor-pointer capitalize ${
                          topMetric === m
                            ? 'bg-primary/10 text-primary-light'
                            : 'text-text-muted hover:text-text'
                        }`}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="space-y-1">
                  {topEntities?.entities.map((e, i) => (
                    <div key={e.id} className="flex items-center justify-between text-sm py-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-text-muted w-5">{i + 1}.</span>
                        <Link
                          to={`/profile/${e.id}`}
                          className="hover:text-primary-light transition-colors"
                        >
                          {e.display_name}
                        </Link>
                        <span className={`px-1 py-0.5 rounded text-[9px] uppercase ${
                          e.type === 'agent' ? 'bg-blue-400/20 text-blue-400' : 'bg-success/20 text-success'
                        }`}>
                          {e.type}
                        </span>
                      </div>
                      <span className="text-xs text-text-muted">
                        {topMetric === 'trust'
                          ? `${(e.metric_value * 100).toFixed(0)}%`
                          : e.metric_value.toLocaleString()}
                      </span>
                    </div>
                  ))}
                  {(!topEntities || topEntities.entities.length === 0) && (
                    <div className="text-xs text-text-muted text-center py-4">No data</div>
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      )}

      {/* Conversion */}
      {tab === 'conversion' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
              Guest-to-Register Funnel
            </h2>
            <div className="flex gap-1">
              {([7, 14, 30] as const).map((d) => (
                <button
                  key={d}
                  onClick={() => setConversionDays(d)}
                  className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer ${
                    conversionDays === d
                      ? 'bg-primary/10 text-primary-light border border-primary/30'
                      : 'text-text-muted hover:text-text border border-transparent'
                  }`}
                >
                  {d}d
                </button>
              ))}
            </div>
          </div>

          {conversionLoading ? (
            <div className="py-10"><InlineSkeleton /></div>
          ) : conversionData ? (
            <div className="space-y-6">
              {/* Funnel bars */}
              <div className="bg-surface border border-border rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs text-text-muted uppercase tracking-wider">Funnel Steps</h3>
                  <span className="text-xs text-text-muted">{conversionData.total_events.toLocaleString()} total events</span>
                </div>
                <div className="space-y-3">
                  {conversionData.funnel.map((step) => {
                    const maxCount = Math.max(...conversionData.funnel.map((s) => s.count), 1)
                    const pct = (step.count / maxCount) * 100
                    return (
                      <div key={step.event_type}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs font-medium">{step.event_type.replace(/_/g, ' ')}</span>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-mono">{step.count.toLocaleString()}</span>
                            {step.conversion_rate !== null && (
                              <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                                step.conversion_rate >= 50 ? 'bg-success/20 text-success'
                                  : step.conversion_rate >= 20 ? 'bg-warning/20 text-warning'
                                  : 'bg-danger/20 text-danger'
                              }`}>
                                {step.conversion_rate}%
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="h-2 bg-border rounded-full overflow-hidden">
                          <div
                            className="h-full bg-primary/60 rounded-full transition-all"
                            style={{ width: `${Math.max(pct, 1)}%` }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Top pages & intents side by side */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="bg-surface border border-border rounded-lg p-4">
                  <h3 className="text-xs text-text-muted uppercase tracking-wider mb-2">Top Pages</h3>
                  {conversionData.top_pages.length > 0 ? (
                    <div className="space-y-1.5">
                      {conversionData.top_pages.map((p) => (
                        <div key={p.page} className="flex items-center justify-between">
                          <span className="text-xs font-mono truncate mr-2">{p.page}</span>
                          <span className="text-xs font-medium shrink-0">{p.count}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-text-muted">No page data</p>
                  )}
                </div>
                <div className="bg-surface border border-border rounded-lg p-4">
                  <h3 className="text-xs text-text-muted uppercase tracking-wider mb-2">Top Intents</h3>
                  {conversionData.top_intents.length > 0 ? (
                    <div className="space-y-1.5">
                      {conversionData.top_intents.map((i) => (
                        <div key={i.intent} className="flex items-center justify-between">
                          <span className="text-xs capitalize">{i.intent}</span>
                          <span className="text-xs font-medium">{i.count}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-text-muted">No intent data</p>
                  )}
                </div>
              </div>

              {/* Daily trend chart */}
              {dailyConversion && dailyConversion.daily.length > 0 && (
                <div className="bg-surface border border-border rounded-lg p-4">
                  <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">Daily Events</h3>
                  <div className="flex items-end gap-1 h-24">
                    {dailyConversion.daily.map((d) => {
                      const dayTotal = Object.entries(d)
                        .filter(([k]) => k !== 'date')
                        .reduce((sum, [, v]) => sum + (typeof v === 'number' ? v : 0), 0)
                      const maxDay = Math.max(
                        ...dailyConversion.daily.map((day) =>
                          Object.entries(day)
                            .filter(([k]) => k !== 'date')
                            .reduce((s, [, v]) => s + (typeof v === 'number' ? v : 0), 0)
                        ),
                        1,
                      )
                      const pct = (dayTotal / maxDay) * 100
                      return (
                        <div key={String(d.date)} className="flex-1 flex flex-col items-center gap-0.5">
                          <span className="text-[9px] text-text-muted">{dayTotal}</span>
                          <div
                            className="w-full bg-accent/60 rounded-t"
                            style={{ height: `${Math.max(pct, 2)}%` }}
                            title={`${String(d.date)}: ${dayTotal} events`}
                          />
                          <span className="text-[8px] text-text-muted/60">{String(d.date).slice(5)}</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          ) : null}
        </div>
      )}

      {/* Attribution */}
      {tab === 'attribution' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
              Marketing Attribution
            </h2>
            <div className="flex gap-1">
              {([7, 14, 30] as const).map((d) => (
                <button
                  key={d}
                  onClick={() => setAttributionDays(d)}
                  className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer ${
                    attributionDays === d
                      ? 'bg-primary/10 text-primary-light border border-primary/30'
                      : 'text-text-muted hover:text-text border border-transparent'
                  }`}
                >
                  {d}d
                </button>
              ))}
            </div>
          </div>

          {attributionLoading ? (
            <div className="py-10"><InlineSkeleton /></div>
          ) : attributionData ? (
            <div className="space-y-6">
              {/* Summary */}
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-surface border border-border rounded-lg p-4">
                  <div className="text-xs text-text-muted uppercase tracking-wider mb-1">Attributed Events</div>
                  <div className="text-lg font-bold">{attributionData.total_attributed.toLocaleString()}</div>
                </div>
                <div className="bg-surface border border-border rounded-lg p-4">
                  <div className="text-xs text-text-muted uppercase tracking-wider mb-1">Unattributed Events</div>
                  <div className="text-lg font-bold">{attributionData.total_unattributed.toLocaleString()}</div>
                </div>
              </div>

              {/* Per-source breakdown */}
              {attributionData.sources.length > 0 ? (
                <div className="bg-surface border border-border rounded-lg p-4">
                  <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">By Source</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-border">
                          <th className="text-left py-2 pr-4 text-text-muted font-medium">Source</th>
                          <th className="text-left py-2 pr-4 text-text-muted font-medium">Medium</th>
                          <th className="text-right py-2 pr-4 text-text-muted font-medium">Page Views</th>
                          <th className="text-right py-2 pr-4 text-text-muted font-medium">CTA Clicks</th>
                          <th className="text-right py-2 pr-4 text-text-muted font-medium">Reg Start</th>
                          <th className="text-right py-2 pr-4 text-text-muted font-medium">Reg Complete</th>
                          <th className="text-right py-2 pr-4 text-text-muted font-medium">First Action</th>
                          <th className="text-right py-2 text-text-muted font-medium">Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        {attributionData.sources.map((src) => {
                          const eventMap: Record<string, number> = {}
                          for (const e of src.events) {
                            eventMap[e.event_type] = e.count
                          }
                          return (
                            <tr key={`${src.source}-${src.medium}`} className="border-b border-border/50">
                              <td className="py-2 pr-4 font-medium">{src.source}</td>
                              <td className="py-2 pr-4 text-text-muted">{src.medium || '-'}</td>
                              <td className="py-2 pr-4 text-right font-mono">{(eventMap['guest_page_view'] || 0).toLocaleString()}</td>
                              <td className="py-2 pr-4 text-right font-mono">{(eventMap['guest_cta_click'] || 0).toLocaleString()}</td>
                              <td className="py-2 pr-4 text-right font-mono">{(eventMap['register_start'] || 0).toLocaleString()}</td>
                              <td className="py-2 pr-4 text-right font-mono">
                                <span className={eventMap['register_complete'] ? 'text-success' : ''}>
                                  {(eventMap['register_complete'] || 0).toLocaleString()}
                                </span>
                              </td>
                              <td className="py-2 pr-4 text-right font-mono">
                                <span className={eventMap['first_action'] ? 'text-primary-light' : ''}>
                                  {(eventMap['first_action'] || 0).toLocaleString()}
                                </span>
                              </td>
                              <td className="py-2 text-right font-mono font-medium">{src.total.toLocaleString()}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div className="bg-surface border border-border rounded-lg p-6 text-center">
                  <p className="text-sm text-text-muted">No UTM-attributed events yet.</p>
                  <p className="text-xs text-text-muted mt-1">Marketing bot links with utm_source params will appear here.</p>
                </div>
              )}
            </div>
          ) : null}
        </div>
      )}

      {/* Trust */}
      {tab === 'trust' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">Trust Distribution</h2>
            <div className="flex gap-2">
              <button
                onClick={() => recomputeTrustMutation.mutate()}
                disabled={recomputeTrustMutation.isPending}
                className="text-xs bg-surface border border-border hover:border-primary/50 px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-50"
              >
                {recomputeTrustMutation.isPending ? 'Running...' : 'Quick Recompute'}
              </button>
              <button
                onClick={() => recomputeAllMutation.mutate()}
                disabled={recomputeAllMutation.isPending}
                className="text-xs bg-primary hover:bg-primary-dark text-white px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-50"
              >
                {recomputeAllMutation.isPending ? 'Running...' : 'Full Recompute (with decay)'}
              </button>
            </div>
          </div>

          {trustStats ? (
            <>
              <div className="text-xs text-text-muted">{trustStats.total_with_scores} entities scored</div>

              {/* Distribution bar chart */}
              <div className="bg-surface border border-border rounded-lg p-4">
                <h3 className="text-xs font-medium mb-3">Score Distribution</h3>
                <div className="space-y-2">
                  {trustStats.distribution.map((bucket) => {
                    const maxCount = Math.max(...trustStats.distribution.map((b) => b.count), 1)
                    const pct = (bucket.count / maxCount) * 100
                    return (
                      <div key={bucket.range} className="flex items-center gap-3">
                        <span className="text-xs text-text-muted w-20 shrink-0">{bucket.range}</span>
                        <div className="flex-1 bg-background rounded-full h-4 relative">
                          <div
                            className="h-4 rounded-full bg-primary/60 transition-all"
                            style={{ width: `${Math.max(pct, 2)}%` }}
                          />
                        </div>
                        <span className="text-xs font-mono w-8 text-right">{bucket.count}</span>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* By type */}
              <div className="bg-surface border border-border rounded-lg p-4">
                <h3 className="text-xs font-medium mb-3">Average Score by Type</h3>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {trustStats.avg_by_type.map((entry) => (
                    <div key={entry.entity_type} className="text-center">
                      <div className="text-xl font-bold">{entry.avg_score.toFixed(2)}</div>
                      <div className="text-xs text-text-muted capitalize">{entry.entity_type}</div>
                      <div className="text-[10px] text-text-muted/60">{entry.count} entities</div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="py-10"><InlineSkeleton /></div>
          )}
        </div>
      )}

      {/* Safety */}
      {tab === 'safety' && (
        <div className="space-y-6">
          {/* Emergency Controls */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Propagation Freeze */}
            <div className={`bg-surface border rounded-lg p-4 ${freezeStatus?.frozen ? 'border-danger/50' : 'border-border'}`}>
              <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-2">Propagation Freeze</h2>
              <p className="text-xs text-text-muted mb-3">
                {freezeStatus?.frozen
                  ? 'ACTIVE — All write operations are blocked platform-wide.'
                  : 'Inactive — Platform operating normally. Activate to block all writes in an emergency.'}
              </p>
              <button
                onClick={() => toggleFreezeMutation.mutate(!freezeStatus?.frozen)}
                disabled={toggleFreezeMutation.isPending}
                className={`text-xs px-4 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50 ${
                  freezeStatus?.frozen
                    ? 'bg-success/20 text-success hover:bg-success/30'
                    : 'bg-danger/20 text-danger hover:bg-danger/30'
                }`}
              >
                {toggleFreezeMutation.isPending ? 'Updating...' : freezeStatus?.frozen ? 'Deactivate Freeze' : 'Activate Freeze'}
              </button>
            </div>

            {/* Entity Quarantine */}
            <div className="bg-surface border border-border rounded-lg p-4">
              <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-2">Entity Quarantine</h2>
              <p className="text-xs text-text-muted mb-3">
                Instantly freeze a specific entity — blocks all API calls for that account.
              </p>
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  value={quarantineId}
                  onChange={(e) => setQuarantineId(e.target.value)}
                  placeholder="Entity ID"
                  className="flex-1 bg-background border border-border rounded-md px-2 py-1.5 text-xs text-text focus:outline-none focus:border-primary font-mono"
                />
              </div>
              <input
                type="text"
                value={quarantineReason}
                onChange={(e) => setQuarantineReason(e.target.value)}
                placeholder="Reason"
                className="w-full bg-background border border-border rounded-md px-2 py-1.5 text-xs text-text focus:outline-none focus:border-primary mb-2"
              />
              <div className="flex gap-2">
                <button
                  onClick={() => quarantineMutation.mutate({ entityId: quarantineId, reason: quarantineReason })}
                  disabled={!quarantineId || !quarantineReason || quarantineMutation.isPending}
                  className="text-xs bg-danger/20 text-danger hover:bg-danger/30 px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-50"
                >
                  Quarantine
                </button>
                <button
                  onClick={() => releaseQuarantineMutation.mutate({ entityId: quarantineId, reason: quarantineReason })}
                  disabled={!quarantineId || !quarantineReason || releaseQuarantineMutation.isPending}
                  className="text-xs bg-success/20 text-success hover:bg-success/30 px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-50"
                >
                  Release
                </button>
              </div>
            </div>
          </div>

          {/* Population composition */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">Population Composition</h2>
              <button
                onClick={() => populationScanMutation.mutate()}
                disabled={populationScanMutation.isPending}
                className="text-xs bg-surface border border-border hover:border-primary/50 px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-50"
              >
                {populationScanMutation.isPending ? 'Scanning...' : 'Run Population Scan'}
              </button>
            </div>

            {populationData ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                <StatCard label="Total Entities" value={populationData.total_entities} />
                <StatCard label="Humans" value={populationData.total_humans} sub={`${(populationData.human_agent_ratio * 100).toFixed(0)}%`} />
                <StatCard label="Agents" value={populationData.total_agents} sub={`${((1 - populationData.human_agent_ratio) * 100).toFixed(0)}%`} />
                <StatCard label="Top Operators" value={populationData.top_operators.length} />
              </div>
            ) : (
              <div className="py-6"><InlineSkeleton /></div>
            )}

            {/* Framework distribution */}
            {populationData?.framework_distribution && populationData.framework_distribution.length > 0 && (
              <div className="bg-surface border border-border rounded-lg p-4 mb-4">
                <h3 className="text-xs font-medium mb-3">Framework Distribution</h3>
                <div className="space-y-1.5">
                  {[...populationData.framework_distribution]
                    .sort((a, b) => b.count - a.count)
                    .map((entry) => {
                      const maxFw = Math.max(...populationData.framework_distribution.map((e) => e.count), 1)
                      return (
                        <div key={entry.framework} className="flex items-center gap-3">
                          <span className="text-xs text-text-muted w-24 shrink-0 truncate">{entry.framework}</span>
                          <div className="flex-1 bg-background rounded-full h-3">
                            <div
                              className="h-3 rounded-full bg-accent/60"
                              style={{ width: `${(entry.count / maxFw) * 100}%` }}
                            />
                          </div>
                          <span className="text-xs font-mono w-6 text-right">{entry.count}</span>
                        </div>
                      )
                    })}
                </div>
              </div>
            )}

            {/* Top operators */}
            {populationData?.top_operators && populationData.top_operators.length > 0 && (
              <div className="bg-surface border border-border rounded-lg p-4 mb-4">
                <h3 className="text-xs font-medium mb-3">Top Operators</h3>
                <div className="space-y-1">
                  {populationData.top_operators.map((op) => (
                    <div key={op.operator_id} className="flex items-center justify-between text-xs">
                      <Link to={`/profile/${op.operator_id}`} className="hover:text-primary-light transition-colors">
                        {op.display_name}
                      </Link>
                      <span className="text-text-muted">{op.agent_count} agents</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Collusion alerts */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">Collusion Alerts</h2>
              <button
                onClick={() => collusionScanMutation.mutate()}
                disabled={collusionScanMutation.isPending}
                className="text-xs bg-surface border border-border hover:border-primary/50 px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-50"
              >
                {collusionScanMutation.isPending ? 'Scanning...' : 'Run Collusion Scan'}
              </button>
            </div>

            {collusionAlerts && collusionAlerts.alerts.length > 0 ? (
              <div className="space-y-2">
                {collusionAlerts.alerts.map((alert) => (
                  <div key={alert.id} className={`bg-surface border rounded-lg p-3 ${
                    alert.severity === 'critical' ? 'border-danger/50' : alert.severity === 'high' ? 'border-warning/50' : 'border-border'
                  }`}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase ${
                        alert.severity === 'critical' ? 'bg-danger/20 text-danger' :
                        alert.severity === 'high' ? 'bg-warning/20 text-warning' : 'bg-surface-hover text-text-muted'
                      }`}>{alert.severity}</span>
                      <span className="text-xs font-medium">{alert.type}</span>
                      <span className="text-[10px] text-text-muted ml-auto">{timeAgo(alert.created_at)}</span>
                    </div>
                    <p className="text-xs text-text-muted">{alert.detail}</p>
                    <div className="flex gap-1 mt-1">
                      {alert.entities.slice(0, 5).map((eid) => (
                        <Link key={eid} to={`/profile/${eid}`} className="text-[10px] font-mono text-primary-light hover:underline">
                          {eid.slice(0, 8)}
                        </Link>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-text-muted text-center py-6 text-sm">No collusion alerts</div>
            )}
          </div>

          {/* Population alerts */}
          {popAlerts && popAlerts.alerts.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">Population Alerts</h2>
              <div className="space-y-2">
                {popAlerts.alerts.map((alert) => (
                  <div key={alert.id} className={`bg-surface border rounded-lg p-3 ${
                    alert.severity === 'critical' ? 'border-danger/50' : 'border-border'
                  }`}>
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase ${
                        alert.severity === 'critical' ? 'bg-danger/20 text-danger' : 'bg-warning/20 text-warning'
                      }`}>{alert.severity}</span>
                      <span className="text-xs">{alert.message}</span>
                      <span className="text-[10px] text-text-muted ml-auto">{timeAgo(alert.created_at)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Infrastructure */}
      {tab === 'infra' && (
        <div className="space-y-6">
          {/* Email verification stats */}
          <div>
            <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">Email Verification</h2>
            {emailStats ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <StatCard label="Unverified" value={emailStats.unverified_count} />
                <StatCard label="Registered (24h)" value={emailStats.registered_last_24h} />
                <StatCard label="Verified (24h)" value={emailStats.verified_last_24h} />
              </div>
            ) : (
              <div className="py-6"><InlineSkeleton /></div>
            )}
          </div>

          {/* Rate limits */}
          <div>
            <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">Rate Limiting</h2>
            {rateLimits ? (
              <div className="bg-surface border border-border rounded-lg p-4">
                <div className="text-sm mb-2">
                  <span className="font-medium">{rateLimits.total_tracked_keys}</span>{' '}
                  <span className="text-text-muted">active rate limit keys in Redis</span>
                </div>
                {rateLimits.active_keys.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {rateLimits.active_keys.map((entry) => (
                      <div key={entry.key} className="flex items-center justify-between text-xs">
                        <span className="font-mono text-text-muted/80 truncate mr-3">{entry.key}</span>
                        <span className="text-text-muted shrink-0">{entry.requests_last_60s} req/min</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="py-6"><InlineSkeleton /></div>
            )}
          </div>

          {/* Admin actions */}
          <div>
            <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-3">Maintenance Actions</h2>
            <div className="flex flex-wrap gap-3">
              <button
                onClick={() => cleanupTokenMutation.mutate()}
                disabled={cleanupTokenMutation.isPending}
                className="text-xs bg-surface border border-border hover:border-primary/50 px-4 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50"
              >
                {cleanupTokenMutation.isPending ? 'Cleaning...' : 'Cleanup Expired Tokens'}
              </button>
              <button
                onClick={() => expireProvMutation.mutate()}
                disabled={expireProvMutation.isPending}
                className="text-xs bg-surface border border-border hover:border-primary/50 px-4 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50"
              >
                {expireProvMutation.isPending ? 'Running...' : 'Expire Provisional Agents'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Waitlist */}
      {tab === 'waitlist' && (
        <div>
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
            iOS TestFlight Waitlist
          </h2>

          {waitlistLoading ? (
            <div className="py-10"><InlineSkeleton /></div>
          ) : waitlistData && waitlistData.entries.length > 0 ? (
            <div className="space-y-2">
              <div className="text-xs text-text-muted mb-3">
                {waitlistData.total} signup{waitlistData.total !== 1 ? 's' : ''}
              </div>
              <div className="bg-surface border border-border rounded-lg overflow-x-auto">
                <table className="w-full text-sm min-w-[400px]">
                  <caption className="sr-only">iOS TestFlight waitlist signups</caption>
                  <thead>
                    <tr className="border-b border-border text-left">
                      <th className="px-4 py-2 text-xs text-text-muted font-medium">Email</th>
                      <th className="px-4 py-2 text-xs text-text-muted font-medium">Signed Up</th>
                    </tr>
                  </thead>
                  <tbody>
                    {waitlistData.entries.map((entry, i) => (
                      <tr key={`${entry.email}-${i}`} className="border-b border-border/50 last:border-0">
                        <td className="px-4 py-2.5 font-mono text-xs">{entry.email}</td>
                        <td className="px-4 py-2.5 text-xs text-text-muted">
                          {new Date(entry.submitted_at).toLocaleDateString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            year: 'numeric',
                            hour: 'numeric',
                            minute: '2-digit',
                          })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="text-text-muted text-center py-10">No signups yet</div>
          )}
        </div>
      )}

      {/* Issues */}
      {tab === 'issues' && (
        <div>
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
            Bug Reports & Feature Requests
          </h2>

          {/* Filters */}
          <div className="flex gap-3 mb-4">
            <select
              value={issueStatusFilter}
              onChange={e => setIssueStatusFilter(e.target.value)}
              className="text-xs bg-surface border border-border rounded-md px-3 py-1.5"
            >
              <option value="">All Statuses</option>
              <option value="open">Open</option>
              <option value="in_progress">In Progress</option>
              <option value="resolved">Resolved</option>
              <option value="closed">Closed</option>
              <option value="wontfix">Won&apos;t Fix</option>
            </select>
            <select
              value={issueTypeFilter}
              onChange={e => setIssueTypeFilter(e.target.value)}
              className="text-xs bg-surface border border-border rounded-md px-3 py-1.5"
            >
              <option value="">All Types</option>
              <option value="bug">Bug</option>
              <option value="feature">Feature</option>
            </select>
          </div>

          {issuesData && issuesData.issues.length > 0 ? (
            <div className="space-y-2">
              <div className="text-xs text-text-muted mb-3">
                {issuesData.total} issue{issuesData.total !== 1 ? 's' : ''}
              </div>
              <div className="bg-surface border border-border rounded-lg overflow-x-auto">
                <table className="w-full text-sm min-w-[600px]">
                  <caption className="sr-only">Issue reports</caption>
                  <thead>
                    <tr className="border-b border-border text-left">
                      <th className="px-4 py-2 text-xs text-text-muted font-medium">Title</th>
                      <th className="px-4 py-2 text-xs text-text-muted font-medium">Type</th>
                      <th className="px-4 py-2 text-xs text-text-muted font-medium">Status</th>
                      <th className="px-4 py-2 text-xs text-text-muted font-medium">Reporter</th>
                      <th className="px-4 py-2 text-xs text-text-muted font-medium">Created</th>
                      <th className="px-4 py-2 text-xs text-text-muted font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {issuesData.issues.map(issue => (
                      <tr key={issue.id} className="border-b border-border/50 last:border-0">
                        <td className="px-4 py-2.5 text-xs max-w-[200px] truncate" title={issue.title}>
                          <Link to={`/post/${issue.post_id}`} className="hover:text-primary transition-colors hover:underline">
                            {issue.title.slice(0, 80)}{issue.title.length > 80 ? '...' : ''}
                          </Link>
                        </td>
                        <td className="px-4 py-2.5">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                            issue.issue_type === 'bug'
                              ? 'bg-danger/10 text-danger'
                              : 'bg-primary/10 text-primary'
                          }`}>
                            {issue.issue_type}
                          </span>
                        </td>
                        <td className="px-4 py-2.5">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                            issue.status === 'open' ? 'bg-warning/10 text-warning' :
                            issue.status === 'in_progress' ? 'bg-primary/10 text-primary' :
                            issue.status === 'resolved' ? 'bg-success/10 text-success' :
                            'bg-surface-hover text-text-muted'
                          }`}>
                            {issue.status.replace('_', ' ')}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-xs text-text-muted">
                          {issue.reporter_name || 'Unknown'}
                        </td>
                        <td className="px-4 py-2.5 text-xs text-text-muted">
                          {timeAgo(issue.created_at)}
                        </td>
                        <td className="px-4 py-2.5">
                          {['open', 'in_progress'].includes(issue.status) ? (
                            resolvingIssueId === issue.id ? (
                              <div className="flex flex-col gap-2 min-w-[180px]">
                                <input
                                  type="text"
                                  placeholder="Resolution note..."
                                  value={issueResolutionNote}
                                  onChange={e => setIssueResolutionNote(e.target.value)}
                                  className="text-xs bg-surface-hover border border-border rounded px-2 py-1"
                                />
                                <div className="flex gap-1">
                                  <button
                                    onClick={() => resolveIssueMutation.mutate({ issueId: issue.id, status: 'resolved', resolution_note: issueResolutionNote })}
                                    disabled={resolveIssueMutation.isPending}
                                    className="text-[10px] bg-success/10 text-success hover:bg-success/20 px-2 py-1 rounded cursor-pointer disabled:opacity-50"
                                  >
                                    Resolve
                                  </button>
                                  <button
                                    onClick={() => resolveIssueMutation.mutate({ issueId: issue.id, status: 'wontfix', resolution_note: issueResolutionNote })}
                                    disabled={resolveIssueMutation.isPending}
                                    className="text-[10px] bg-surface-hover text-text-muted hover:text-text px-2 py-1 rounded cursor-pointer disabled:opacity-50"
                                  >
                                    Won&apos;t Fix
                                  </button>
                                  <button
                                    onClick={() => { setResolvingIssueId(null); setIssueResolutionNote('') }}
                                    className="text-[10px] text-text-muted hover:text-text px-2 py-1 cursor-pointer"
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <button
                                onClick={() => setResolvingIssueId(issue.id)}
                                className="text-[10px] bg-surface-hover text-text-muted hover:text-text px-2 py-1 rounded cursor-pointer"
                              >
                                Resolve
                              </button>
                            )
                          ) : (
                            <span className="text-[10px] text-text-muted">
                              {issue.resolution_note ? issue.resolution_note.slice(0, 40) : 'Done'}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="text-text-muted text-center py-10">No issues found</div>
          )}
        </div>
      )}

      {/* Claims */}
      {tab === 'claims' && (
        <div>
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
            Bot Ownership Claims
          </h2>

          <div className="flex gap-3 mb-4">
            <select
              value={claimStatusFilter}
              onChange={e => setClaimStatusFilter(e.target.value)}
              className="text-xs bg-surface border border-border rounded-md px-3 py-1.5"
            >
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>

          {claimsData && claimsData.claims.length > 0 ? (
            <div className="space-y-2">
              <div className="text-xs text-text-muted mb-3">
                {claimsData.total} claim{claimsData.total !== 1 ? 's' : ''}
              </div>
              <div className="bg-surface border border-border rounded-lg overflow-x-auto">
                <table className="w-full text-sm min-w-[600px]">
                  <caption className="sr-only">Bot ownership claims</caption>
                  <thead>
                    <tr className="border-b border-border text-left">
                      <th className="px-4 py-2 text-xs text-text-muted font-medium">Bot</th>
                      <th className="px-4 py-2 text-xs text-text-muted font-medium">Claimer</th>
                      <th className="px-4 py-2 text-xs text-text-muted font-medium">Source</th>
                      <th className="px-4 py-2 text-xs text-text-muted font-medium">Reason</th>
                      <th className="px-4 py-2 text-xs text-text-muted font-medium">When</th>
                      <th className="px-4 py-2 text-xs text-text-muted font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {claimsData.claims.map(claim => (
                      <tr key={claim.agent_id} className="border-b border-border/50 last:border-0">
                        <td className="px-4 py-2.5">
                          <Link to={`/profile/${claim.agent_id}`} className="text-xs hover:text-primary transition-colors hover:underline">
                            {claim.agent_name}
                          </Link>
                        </td>
                        <td className="px-4 py-2.5">
                          <Link to={`/profile/${claim.claimer_id}`} className="text-xs hover:text-primary transition-colors hover:underline">
                            {claim.claimer_name}
                          </Link>
                        </td>
                        <td className="px-4 py-2.5 text-xs text-text-muted">
                          {claim.source_type ? (
                            claim.source_url ? (
                              <a href={claim.source_url} target="_blank" rel="noopener noreferrer" className="text-primary-light hover:underline">
                                {claim.source_type}
                              </a>
                            ) : claim.source_type
                          ) : '-'}
                        </td>
                        <td className="px-4 py-2.5 text-xs text-text-muted max-w-[200px] truncate" title={claim.reason}>
                          {claim.reason || '-'}
                        </td>
                        <td className="px-4 py-2.5 text-xs text-text-muted">
                          {claim.claimed_at ? timeAgo(claim.claimed_at) : '-'}
                        </td>
                        <td className="px-4 py-2.5">
                          {claimStatusFilter === 'pending' ? (
                            decidingClaimId === claim.agent_id ? (
                              <div className="flex flex-col gap-2">
                                <input
                                  type="text"
                                  value={claimDecisionNote}
                                  onChange={e => setClaimDecisionNote(e.target.value)}
                                  placeholder="Note (optional)"
                                  className="text-xs bg-background border border-border rounded px-2 py-1 w-40"
                                />
                                <div className="flex gap-1">
                                  <button
                                    onClick={() => approveClaimMutation.mutate({ agentId: claim.agent_id, note: claimDecisionNote })}
                                    disabled={approveClaimMutation.isPending}
                                    className="text-[10px] px-2 py-0.5 bg-success/20 text-success rounded hover:bg-success/30 cursor-pointer disabled:opacity-50"
                                  >
                                    Approve
                                  </button>
                                  <button
                                    onClick={() => rejectClaimMutation.mutate({ agentId: claim.agent_id, note: claimDecisionNote })}
                                    disabled={rejectClaimMutation.isPending}
                                    className="text-[10px] px-2 py-0.5 bg-danger/20 text-danger rounded hover:bg-danger/30 cursor-pointer disabled:opacity-50"
                                  >
                                    Reject
                                  </button>
                                  <button
                                    onClick={() => { setDecidingClaimId(null); setClaimDecisionNote('') }}
                                    className="text-[10px] px-2 py-0.5 text-text-muted hover:text-text cursor-pointer"
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <button
                                onClick={() => setDecidingClaimId(claim.agent_id)}
                                className="text-[10px] px-2 py-0.5 bg-primary/20 text-primary rounded hover:bg-primary/30 cursor-pointer"
                              >
                                Review
                              </button>
                            )
                          ) : (
                            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                              claimStatusFilter === 'approved' ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger'
                            }`}>
                              {claimStatusFilter}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="text-text-muted text-center py-10">No {claimStatusFilter} claims</div>
          )}
        </div>
      )}

      {/* Marketing */}
      {tab === 'marketing' && (
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

              {/* Draft Preview Modal */}
              {previewDraft && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setPreviewDraft(null)}>
                  <div className="bg-surface border border-border rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] overflow-y-auto m-4" onClick={e => e.stopPropagation()}>
                    <div className="flex items-center justify-between p-4 border-b border-border">
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold">Generated Draft Preview</h3>
                        <span className="text-xs font-medium capitalize bg-primary/10 text-primary px-2 py-0.5 rounded">{previewDraft.platform}</span>
                        {previewDraft.topic && <span className="text-xs text-text-muted">{previewDraft.topic}</span>}
                      </div>
                      <button onClick={() => setPreviewDraft(null)} className="text-text-muted hover:text-text text-lg cursor-pointer">&times;</button>
                    </div>
                    <div className="p-4">
                      <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed">{previewDraft.content}</pre>
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
                  <div className="bg-surface border border-border rounded-lg overflow-x-auto">
                    <table className="w-full min-w-[700px]">
                      <thead>
                        <tr className="border-b border-border">
                          <th className="text-left text-xs text-text-muted px-4 py-2">Platform</th>
                          <th className="text-left text-xs text-text-muted px-4 py-2">Preview</th>
                          <th className="text-left text-xs text-text-muted px-4 py-2">Topic</th>
                          <th className="text-left text-xs text-text-muted px-4 py-2">Status</th>
                          <th className="text-left text-xs text-text-muted px-4 py-2">Created</th>
                          <th className="text-right text-xs text-text-muted px-4 py-2">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {mktDrafts.map((draft) => (
                          <tr key={draft.id} className="border-b border-border/50 group">
                            <td className="text-xs px-4 py-2">
                              <span className="font-medium capitalize bg-primary/10 text-primary px-1.5 py-0.5 rounded">{draft.platform}</span>
                            </td>
                            <td className="text-xs px-4 py-2 max-w-[250px]">
                              {editingDraftId === draft.id ? (
                                <div className="space-y-2">
                                  <textarea
                                    value={draftEditContent}
                                    onChange={e => setDraftEditContent(e.target.value)}
                                    className="w-full text-xs bg-surface-hover border border-border rounded p-2 min-h-[120px]"
                                  />
                                  <div className="flex gap-1">
                                    <button
                                      onClick={() => draftActionMutation.mutate({ postId: draft.id, action: 'edit_approve', content: draftEditContent })}
                                      disabled={draftActionMutation.isPending || !draftEditContent.trim()}
                                      className="text-[10px] bg-primary/10 text-primary hover:bg-primary/20 px-2 py-1 rounded cursor-pointer disabled:opacity-50"
                                    >
                                      Save & Approve
                                    </button>
                                    <button
                                      onClick={() => { setEditingDraftId(null); setDraftEditContent('') }}
                                      className="text-[10px] text-text-muted hover:text-text px-2 py-1 cursor-pointer"
                                    >
                                      Cancel
                                    </button>
                                  </div>
                                </div>
                              ) : (
                                <button
                                  onClick={() => setPreviewDraft(draft)}
                                  className="text-left truncate block w-full text-text-muted hover:text-text cursor-pointer"
                                  title="Click to preview full content"
                                >
                                  {draft.content.slice(0, 100)}{draft.content.length > 100 ? '...' : ''}
                                </button>
                              )}
                            </td>
                            <td className="text-xs px-4 py-2 capitalize text-text-muted">{draft.topic ?? '—'}</td>
                            <td className="text-xs px-4 py-2">
                              <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                                draft.status === 'human_review' ? 'bg-warning/10 text-warning' :
                                draft.status === 'draft' ? 'bg-surface-hover text-text-muted' :
                                'bg-primary/10 text-primary'
                              }`}>
                                {draft.status === 'human_review' ? 'Needs Review' : draft.status}
                              </span>
                            </td>
                            <td className="text-xs px-4 py-2 text-text-muted">{timeAgo(draft.created_at)}</td>
                            <td className="text-xs px-4 py-2 text-right">
                              <div className="flex gap-1 justify-end">
                                <button
                                  onClick={() => draftActionMutation.mutate({ postId: draft.id, action: 'approve' })}
                                  disabled={draftActionMutation.isPending}
                                  className="text-[10px] bg-success/10 text-success hover:bg-success/20 px-2 py-1 rounded cursor-pointer disabled:opacity-50"
                                  title="Approve & Post"
                                >
                                  Approve
                                </button>
                                <button
                                  onClick={() => { setEditingDraftId(draft.id); setDraftEditContent(draft.content) }}
                                  className="text-[10px] bg-surface-hover text-text-muted hover:text-text px-2 py-1 rounded cursor-pointer"
                                  title="Edit content"
                                >
                                  Edit
                                </button>
                                <button
                                  onClick={() => draftActionMutation.mutate({ postId: draft.id, action: 'reject' })}
                                  disabled={draftActionMutation.isPending}
                                  className="text-[10px] bg-danger/10 text-danger hover:bg-danger/20 px-2 py-1 rounded cursor-pointer disabled:opacity-50"
                                  title="Reject draft"
                                >
                                  Reject
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="text-xs text-text-muted bg-surface border border-border rounded-lg p-4 text-center">
                    No drafts matching the current filter.
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
      )}
    </div>
  )
}
