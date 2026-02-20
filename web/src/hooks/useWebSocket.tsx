import { useEffect, useRef, useMemo, useState } from 'react'

type MessageHandler = (data: Record<string, unknown>) => void

interface UseWebSocketOptions {
  channels?: string[]
  onMessage?: MessageHandler
  enabled?: boolean
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const { channels = ['feed', 'notifications'], onMessage, enabled = true } = options
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const mountedRef = useRef(true)
  const onMessageRef = useRef(onMessage)
  const [connected, setConnected] = useState(false)

  // Stabilize channels reference — only change when the actual values change
  const channelKey = channels.join(',')
  const stableChannels = useMemo(() => channels, [channelKey]) // eslint-disable-line react-hooks/exhaustive-deps

  // Keep onMessage ref current without triggering reconnects
  onMessageRef.current = onMessage

  useEffect(() => {
    mountedRef.current = true

    const connect = () => {
      const token = localStorage.getItem('token')
      if (!token || !enabled || !mountedRef.current) return

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const host = window.location.host
      const channelStr = stableChannels.join(',')
      const url = `${protocol}//${host}/api/v1/ws?token=${encodeURIComponent(token)}&channels=${channelStr}`

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'ping') {
            ws.send(JSON.stringify({ type: 'pong' }))
            return
          }
          onMessageRef.current?.(data)
        } catch {
          // ignore non-JSON messages
        }
      }

      ws.onclose = () => {
        setConnected(false)
        wsRef.current = null
        if (mountedRef.current) {
          reconnectTimer.current = setTimeout(connect, 3000)
        }
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()
    return () => {
      mountedRef.current = false
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [stableChannels, enabled])

  return { connected }
}
