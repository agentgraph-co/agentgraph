import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useWebSocket } from '../hooks/useWebSocket'
import { useToast } from './Toasts'
import { useAuth } from '../hooks/useAuth'

export function LiveUpdates() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { addToast } = useToast()

  const onMessage = useCallback(
    (data: Record<string, unknown>) => {
      const channel = data.channel as string | undefined
      const type = data.type as string | undefined

      if (channel === 'feed') {
        if (type === 'new_post') {
          queryClient.invalidateQueries({ queryKey: ['feed'] })
        } else if (type === 'vote_update') {
          queryClient.invalidateQueries({ queryKey: ['feed'] })
          const postId = data.post_id as string | undefined
          if (postId) {
            queryClient.invalidateQueries({ queryKey: ['post', postId] })
          }
        }
      }

      if (channel === 'notifications' && type === 'notification') {
        queryClient.invalidateQueries({ queryKey: ['notifications'] })
        const message = data.message as string | undefined
        if (message) {
          addToast(message)
        }
      }

      if (channel === 'messages') {
        queryClient.invalidateQueries({ queryKey: ['conversations'] })
        queryClient.invalidateQueries({ queryKey: ['messages'] })
        addToast('New message received')
      }

      if (channel === 'marketplace' && type === 'purchase') {
        queryClient.invalidateQueries({ queryKey: ['marketplace'] })
      }

      if (channel === 'activity') {
        queryClient.invalidateQueries({ queryKey: ['profile-activity'] })
        if (type === 'trust_updated') {
          queryClient.invalidateQueries({ queryKey: ['trust-detail'] })
          queryClient.invalidateQueries({ queryKey: ['profile'] })
        }
      }
    },
    [queryClient, addToast],
  )

  useWebSocket({
    channels: ['feed', 'notifications', 'messages', 'marketplace', 'activity'],
    onMessage,
    enabled: !!user,
  })

  return null
}
