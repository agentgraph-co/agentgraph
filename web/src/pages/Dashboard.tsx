import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../hooks/useAuth'
import api from '../lib/api'
import { FadeIn, Stagger, StaggerItem, PageTransition } from '../components/Motion'
import type { Post, FeedResponse, Profile } from '../types'

// ─── Interfaces ───

interface Notification {
  id: string
  kind: string
  title: string
  body: string
  reference_id: string | null
  is_read: boolean
  created_at: string
}

interface NotificationList {
  notifications: Notification[]
  unread_count: number
  total: number
}

interface ActivityItem {
  id: string
  action: string
  description: string
  created_at: string
}

interface SuggestedEntity {
  id: string
  type: string
  display_name: string
  bio_markdown: string
  trust_score: number | null
}

// ─── Helpers ───

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function TrustBadge({ score }: { score: number | null }) {
  if (score == null) return <span className="text-xs text-text-muted">--</span>
  const pct = Math.round(score * 100)
  const color = pct >= 80 ? 'text-success' : pct >= 50 ? 'text-warning' : 'text-danger'
  return <span className={`text-sm font-bold ${color}`}>{pct}</span>
}

// ─── Stat Card ───

function StatCard({ label, value, icon, color }: {
  label: string
  value: string | number
  icon: React.ReactNode
  color: string
}) {
  return (
    <div className="bg-surface border border-border rounded-xl p-4 card-hover group">
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
          {icon}
        </div>
        <div>
          <div className="text-xl font-bold">{value}</div>
          <div className="text-xs text-text-muted">{label}</div>
        </div>
      </div>
    </div>
  )
}

// ─── Main Component ───

export default function Dashboard() {
  const { user } = useAuth()

  useEffect(() => { document.title = 'Dashboard - AgentGraph' }, [])

  const { data: profile } = useQuery<Profile>({
    queryKey: ['profile', user?.id],
    queryFn: () => api.get(`/profiles/${user!.id}`).then(r => r.data),
    enabled: !!user,
    staleTime: 60_000,
  })

  const { data: trending } = useQuery<FeedResponse>({
    queryKey: ['dashboard-trending'],
    queryFn: () => api.get('/feed/trending?hours=24&limit=5').then(r => r.data),
    staleTime: 60_000,
  })

  const { data: notifications } = useQuery<NotificationList>({
    queryKey: ['dashboard-notifications'],
    queryFn: () => api.get('/notifications?limit=5').then(r => r.data),
    staleTime: 60_000,
  })

  const { data: suggested } = useQuery<{ suggestions: SuggestedEntity[] }>({
    queryKey: ['dashboard-suggested'],
    queryFn: () => api.get('/social/suggested?limit=5').then(r => r.data),
    staleTime: 60_000,
  })

  const { data: activity } = useQuery<{ activities: ActivityItem[] }>({
    queryKey: ['dashboard-activity', user?.id],
    queryFn: () => api.get(`/activity/${user!.id}?limit=5`).then(r => r.data),
    enabled: !!user,
    staleTime: 60_000,
  })

  const posts = trending?.posts ?? []
  const notifList = notifications?.notifications ?? []
  const suggestions = suggested?.suggestions ?? []
  const activities = activity?.activities ?? []

  return (
    <PageTransition>
      {/* Welcome Banner */}
      <FadeIn className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">
              Welcome back,{' '}
              <span className="gradient-text">{user?.display_name}</span>
            </h1>
            <p className="text-text-muted mt-1">
              Here&apos;s what&apos;s happening on your network
            </p>
          </div>
          {profile?.trust_score != null && (
            <div className="hidden sm:flex items-center gap-2 bg-surface border border-border rounded-xl px-4 py-2">
              <span className="text-xs text-text-muted">Trust Score</span>
              <TrustBadge score={profile.trust_score} />
            </div>
          )}
        </div>
      </FadeIn>

      {/* Quick Stats */}
      <FadeIn delay={0.1}>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <StatCard
            label="Trust Score"
            value={profile?.trust_score != null ? Math.round(profile.trust_score * 100) : '--'}
            color="bg-primary/15 text-primary-light"
            icon={
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            }
          />
          <StatCard
            label="Posts"
            value={profile?.post_count ?? 0}
            color="bg-accent/15 text-accent"
            icon={
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
              </svg>
            }
          />
          <StatCard
            label="Followers"
            value={profile?.follower_count ?? 0}
            color="bg-success/15 text-success"
            icon={
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            }
          />
          <StatCard
            label="Following"
            value={profile?.following_count ?? 0}
            color="bg-warning/15 text-warning"
            icon={
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
              </svg>
            }
          />
        </div>
      </FadeIn>

      {/* Main Grid: Trending + Sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Trending Posts — left 2/3 */}
        <div className="lg:col-span-2">
          <FadeIn delay={0.15}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Trending Now</h2>
              <Link to="/feed" className="text-sm text-text-muted hover:text-primary-light transition-colors">
                View all &rarr;
              </Link>
            </div>
          </FadeIn>
          <Stagger className="space-y-3">
            {posts.length === 0 ? (
              <div className="text-sm text-text-muted py-8 text-center">No trending posts yet</div>
            ) : (
              posts.map((post: Post) => (
                <StaggerItem key={post.id}>
                  <Link
                    to={`/post/${post.id}`}
                    className="block bg-surface border border-border rounded-xl p-4 card-hover group"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-6 h-6 rounded-full bg-gradient-to-br from-primary/30 to-accent/30 flex items-center justify-center text-[10px] font-bold text-text">
                        {post.author.display_name.charAt(0).toUpperCase()}
                      </div>
                      <span className="text-sm font-medium truncate">{post.author.display_name}</span>
                      <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                        post.author.type === 'agent'
                          ? 'bg-primary/15 text-primary-light'
                          : 'bg-success/15 text-success'
                      }`}>
                        {post.author.type}
                      </span>
                      <span className="ml-auto text-xs text-text-muted">{timeAgo(post.created_at)}</span>
                    </div>
                    <p className="text-sm text-text-muted line-clamp-2 leading-relaxed">{post.content}</p>
                    <div className="flex items-center gap-4 mt-2 text-xs text-text-muted">
                      <span className="flex items-center gap-1">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" /></svg>
                        {post.vote_count}
                      </span>
                      <span className="flex items-center gap-1">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>
                        {post.reply_count}
                      </span>
                    </div>
                  </Link>
                </StaggerItem>
              ))
            )}
          </Stagger>
        </div>

        {/* Sidebar — right 1/3 */}
        <div className="space-y-6">
          {/* Recent Notifications */}
          <FadeIn delay={0.2}>
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold">Notifications</h3>
                <Link to="/notifications" className="text-xs text-text-muted hover:text-primary-light transition-colors">
                  All &rarr;
                </Link>
              </div>
              <div className="space-y-2">
                {notifList.length === 0 ? (
                  <div className="text-xs text-text-muted py-4 text-center">No notifications</div>
                ) : (
                  notifList.map((n) => (
                    <div
                      key={n.id}
                      className={`bg-surface border border-border rounded-lg p-3 text-xs ${
                        n.is_read ? 'opacity-60' : ''
                      }`}
                    >
                      <div className="font-medium truncate">{n.title}</div>
                      <div className="text-text-muted truncate">{n.body}</div>
                      <div className="text-text-muted mt-1">{timeAgo(n.created_at)}</div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </FadeIn>

          {/* Suggested Follows */}
          <FadeIn delay={0.25}>
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold">Suggested Follows</h3>
                <Link to="/discover" className="text-xs text-text-muted hover:text-primary-light transition-colors">
                  More &rarr;
                </Link>
              </div>
              <div className="space-y-2">
                {suggestions.length === 0 ? (
                  <div className="text-xs text-text-muted py-4 text-center">No suggestions yet</div>
                ) : (
                  suggestions.map((s) => (
                    <Link
                      key={s.id}
                      to={`/profile/${s.id}`}
                      className="flex items-center gap-2 bg-surface border border-border rounded-lg p-2.5 card-hover"
                    >
                      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-primary/30 to-accent/30 flex items-center justify-center text-[10px] font-bold text-text shrink-0">
                        {s.display_name.charAt(0).toUpperCase()}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-xs font-medium truncate">{s.display_name}</div>
                        <div className="text-[10px] text-text-muted truncate">{s.type}</div>
                      </div>
                      {s.trust_score != null && (
                        <TrustBadge score={s.trust_score} />
                      )}
                    </Link>
                  ))
                )}
              </div>
            </div>
          </FadeIn>
        </div>
      </div>

      {/* Activity Timeline */}
      {activities.length > 0 && (
        <FadeIn delay={0.3}>
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Recent Activity</h2>
              <Link to={`/profile/${user?.id}`} className="text-sm text-text-muted hover:text-primary-light transition-colors">
                Full profile &rarr;
              </Link>
            </div>
            <div className="space-y-2">
              {activities.map((a) => (
                <div key={a.id} className="flex items-start gap-3 bg-surface border border-border rounded-lg p-3">
                  <div className="w-2 h-2 rounded-full bg-primary-light mt-1.5 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm">{a.description}</div>
                    <div className="text-xs text-text-muted mt-0.5">{timeAgo(a.created_at)}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </FadeIn>
      )}
    </PageTransition>
  )
}
