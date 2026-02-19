import { useEffect, useRef, useCallback, useState } from 'react'

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
  const [connected, setConnected] = useState(false)

  const connect = useCallback(() => {
    const token = localStorage.getItem('token')
    if (!token || !enabled) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const channelStr = channels.join(',')
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
        onMessage?.(data)
      } catch {
        // ignore non-JSON messages
      }
    }

    ws.onclose = () => {
      setConnected(false)
      wsRef.current = null
      reconnectTimer.current = setTimeout(connect, 3000)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [channels, onMessage, enabled])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [connect])

  return { connected }
}
