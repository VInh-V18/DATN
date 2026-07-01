import { useEffect, useRef } from 'react'
import { wsUrl } from '../api/client'

export interface LiveEvent {
  type: string
  payload: unknown
}

export function useLiveEvents(onEvent: (event: LiveEvent) => void) {
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent

  useEffect(() => {
    let socket: WebSocket | null = null
    try {
      socket = new WebSocket(wsUrl)
      socket.onmessage = (message) => {
        try {
          const parsed = JSON.parse(message.data) as LiveEvent
          handlerRef.current(parsed)
        } catch {
          // ignore malformed events
        }
      }
    } catch {
      // WebSocket không khả dụng (ví dụ backend chưa chạy) - bỏ qua realtime.
    }
    return () => socket?.close()
  }, [])
}
