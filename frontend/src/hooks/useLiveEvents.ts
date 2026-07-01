import { useEffect, useRef, useState } from 'react'
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

/** Trạng thái kết nối WebSocket dùng cho chỉ báo online/offline trên sidebar. */
export function useConnectionStatus(): boolean {
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let socket: WebSocket | null = null
    let cancelled = false
    try {
      socket = new WebSocket(wsUrl)
      socket.onopen = () => !cancelled && setConnected(true)
      socket.onclose = () => !cancelled && setConnected(false)
      socket.onerror = () => !cancelled && setConnected(false)
    } catch {
      setConnected(false)
    }
    return () => {
      cancelled = true
      socket?.close()
    }
  }, [])

  return connected
}
