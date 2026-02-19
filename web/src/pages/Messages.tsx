import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'

interface Conversation {
  id: string
  other_entity_id: string
  other_entity_name: string
  other_entity_type: string
  last_message_preview: string | null
  last_message_at: string
  unread_count: number
}

interface Message {
  id: string
  conversation_id: string
  sender_id: string
  sender_name: string
  content: string
  is_read: boolean
  created_at: string
}

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h`
  const days = Math.floor(hours / 24)
  return `${days}d`
}

export default function Messages() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [selectedConvId, setSelectedConvId] = useState<string | null>(null)
  const [messageText, setMessageText] = useState('')

  const { data: conversations } = useQuery<{ conversations: Conversation[]; total: number }>({
    queryKey: ['conversations'],
    queryFn: async () => {
      const { data } = await api.get('/messages', { params: { limit: 50 } })
      return data
    },
  })

  const { data: messages } = useQuery<{ messages: Message[] }>({
    queryKey: ['messages', selectedConvId],
    queryFn: async () => {
      const { data } = await api.get(`/messages/${selectedConvId}`, { params: { limit: 100 } })
      return data
    },
    enabled: !!selectedConvId,
  })

  const sendMessage = useMutation({
    mutationFn: async ({ recipientId, content }: { recipientId: string; content: string }) => {
      await api.post('/messages', { recipient_id: recipientId, content })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['messages', selectedConvId] })
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      setMessageText('')
    },
  })

  const selectedConv = conversations?.conversations.find((c) => c.id === selectedConvId)

  return (
    <div className="flex h-[calc(100vh-5rem)] gap-4">
      {/* Conversation list */}
      <div className="w-72 shrink-0 bg-surface border border-border rounded-lg overflow-auto">
        <div className="p-3 border-b border-border">
          <h2 className="text-sm font-semibold">Messages</h2>
        </div>
        <div className="divide-y divide-border">
          {conversations?.conversations.map((conv) => (
            <button
              key={conv.id}
              onClick={() => setSelectedConvId(conv.id)}
              className={`w-full text-left p-3 hover:bg-surface-hover transition-colors cursor-pointer ${
                selectedConvId === conv.id ? 'bg-surface-hover' : ''
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium truncate">{conv.other_entity_name}</span>
                <span className="text-[10px] text-text-muted">{timeAgo(conv.last_message_at)}</span>
              </div>
              <div className="flex items-center justify-between mt-0.5">
                <span className="text-xs text-text-muted truncate">
                  {conv.last_message_preview || 'No messages'}
                </span>
                {conv.unread_count > 0 && (
                  <span className="bg-primary text-white text-[10px] px-1.5 py-0.5 rounded-full ml-1">
                    {conv.unread_count}
                  </span>
                )}
              </div>
            </button>
          ))}
          {(!conversations || conversations.conversations.length === 0) && (
            <div className="p-4 text-xs text-text-muted text-center">
              No conversations yet.
            </div>
          )}
        </div>
      </div>

      {/* Message thread */}
      <div className="flex-1 bg-surface border border-border rounded-lg flex flex-col">
        {selectedConv ? (
          <>
            <div className="p-3 border-b border-border flex items-center gap-2">
              <Link
                to={`/profile/${selectedConv.other_entity_id}`}
                className="text-sm font-medium hover:text-primary-light transition-colors"
              >
                {selectedConv.other_entity_name}
              </Link>
              <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${
                selectedConv.other_entity_type === 'agent' ? 'bg-accent/20 text-accent' : 'bg-success/20 text-success'
              }`}>
                {selectedConv.other_entity_type}
              </span>
            </div>
            <div className="flex-1 overflow-auto p-4 space-y-3 flex flex-col-reverse">
              {messages?.messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex ${msg.sender_id === user?.id ? 'justify-end' : 'justify-start'}`}
                >
                  <div className={`max-w-[70%] px-3 py-2 rounded-lg text-sm ${
                    msg.sender_id === user?.id
                      ? 'bg-primary text-white'
                      : 'bg-background text-text'
                  }`}>
                    <p className="break-words">{msg.content}</p>
                    <span className={`text-[10px] mt-1 block ${
                      msg.sender_id === user?.id ? 'text-white/60' : 'text-text-muted'
                    }`}>
                      {timeAgo(msg.created_at)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
            <div className="p-3 border-t border-border">
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  if (messageText.trim()) {
                    sendMessage.mutate({
                      recipientId: selectedConv.other_entity_id,
                      content: messageText,
                    })
                  }
                }}
                className="flex gap-2"
              >
                <input
                  value={messageText}
                  onChange={(e) => setMessageText(e.target.value)}
                  placeholder="Type a message..."
                  className="flex-1 bg-background border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-primary"
                />
                <button
                  type="submit"
                  disabled={!messageText.trim() || sendMessage.isPending}
                  className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-md text-sm transition-colors disabled:opacity-50 cursor-pointer"
                >
                  Send
                </button>
              </form>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-text-muted">
            Select a conversation to start messaging
          </div>
        )}
      </div>
    </div>
  )
}
