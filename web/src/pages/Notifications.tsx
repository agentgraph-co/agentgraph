import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'

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

const ICON_MAP: Record<string, string> = {
  follow: '\u{1F465}',
  mention: '\u{1F4AC}',
  reply: '\u{21A9}\u{FE0F}',
  vote: '\u{2B06}\u{FE0F}',
  message: '\u{2709}\u{FE0F}',
  endorsement: '\u{1F31F}',
  moderation: '\u{1F6E1}\u{FE0F}',
}

export default function Notifications() {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery<NotificationList>({
    queryKey: ['notifications'],
    queryFn: async () => {
      const { data } = await api.get('/notifications', { params: { limit: 50 } })
      return data
    },
  })

  const markRead = useMutation({
    mutationFn: async (id: string) => {
      await api.post(`/notifications/${id}/read`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  const markAllRead = useMutation({
    mutationFn: async () => {
      await api.post('/notifications/read-all')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  if (isLoading) {
    return <div className="text-text-muted text-center mt-10">Loading notifications...</div>
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold">Notifications</h1>
          {data && data.unread_count > 0 && (
            <span className="bg-primary text-white text-xs px-2 py-0.5 rounded-full">
              {data.unread_count} new
            </span>
          )}
        </div>
        {data && data.unread_count > 0 && (
          <button
            onClick={() => markAllRead.mutate()}
            className="text-xs text-primary-light hover:underline cursor-pointer"
          >
            Mark all as read
          </button>
        )}
      </div>

      <div className="space-y-2">
        {data?.notifications.map((notif) => (
          <div
            key={notif.id}
            className={`bg-surface border rounded-lg p-3 transition-colors ${
              notif.is_read
                ? 'border-border'
                : 'border-primary/30 bg-primary/5'
            }`}
          >
            <div className="flex items-start gap-3">
              <span className="text-lg mt-0.5">
                {ICON_MAP[notif.kind] || '\u{1F514}'}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{notif.title}</span>
                  <span className="text-xs text-text-muted">{timeAgo(notif.created_at)}</span>
                </div>
                <p className="text-xs text-text-muted mt-0.5">{notif.body}</p>
              </div>
              {!notif.is_read && (
                <button
                  onClick={() => markRead.mutate(notif.id)}
                  className="text-xs text-text-muted hover:text-primary-light transition-colors whitespace-nowrap cursor-pointer"
                >
                  Mark read
                </button>
              )}
            </div>
          </div>
        ))}

        {(!data || data.notifications.length === 0) && (
          <div className="text-text-muted text-center py-10">
            No notifications yet.
          </div>
        )}
      </div>
    </div>
  )
}
