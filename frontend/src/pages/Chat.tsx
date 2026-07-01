import { useEffect, useRef, useState } from 'react'
import { Bot, Send, User } from 'lucide-react'
import { sendChatMessage } from '../api/client'
import type { ChatMessageTurn } from '../api/types'

export default function ChatPage() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessageTurn[]>([])
  const [input, setInput] = useState('')
  const [pendingConfirmation, setPendingConfirmation] = useState(false)
  const [loading, setLoading] = useState(false)
  const windowRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    windowRef.current?.scrollTo({ top: windowRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, loading, pendingConfirmation])

  const send = async () => {
    if (!input.trim() || loading) return
    const userMessage = input
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }])
    setInput('')
    setPendingConfirmation(false)
    setLoading(true)
    try {
      const response = await sendChatMessage(userMessage, sessionId)
      setSessionId(response.session_id)
      setMessages((prev) => [...prev, { role: 'assistant', content: response.reply }])
      setPendingConfirmation(response.requires_confirmation)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fade-in chat-page">
      <div className="page-header">
        <div>
          <h1>Copilot hội thoại</h1>
          <p className="hint" style={{ margin: '6px 0 0' }}>
            Hỏi đáp bằng tiếng Việt về trạng thái mạng. Hành động thay đổi cấu hình luôn cần bạn xác nhận trước khi thực thi.
          </p>
        </div>
      </div>

      <div className="chat-window" ref={windowRef}>
        {messages.length === 0 && (
          <div className="chat-row chat-row-assistant">
            <div className="chat-avatar assistant">
              <Bot size={15} />
            </div>
            <div className="chat-bubble">
              Xin chào! Bạn có thể hỏi tôi về trạng thái thiết bị, sự cố hoặc cảnh báo an ninh — ví dụ
              "Vì sao R3 không kết nối được tới R1?".
            </div>
          </div>
        )}

        {messages.map((message, idx) => (
          <div key={idx} className={`chat-row chat-row-${message.role}`}>
            <div className={`chat-avatar ${message.role}`}>{message.role === 'user' ? <User size={15} /> : <Bot size={15} />}</div>
            <div className="chat-bubble">{message.content}</div>
          </div>
        ))}

        {loading && (
          <div className="chat-row chat-row-assistant">
            <div className="chat-avatar assistant">
              <Bot size={15} />
            </div>
            <div className="chat-bubble">
              <span className="chat-typing">
                <span />
                <span />
                <span />
              </span>
            </div>
          </div>
        )}

        {pendingConfirmation && (
          <div className="chat-row chat-row-system">
            <div className="chat-bubble">Agent đang chờ xác nhận — trả lời "có" để thực hiện hoặc "không" để hủy.</div>
          </div>
        )}
      </div>

      <div className="chat-input-row">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder="Vì sao R3 không kết nối được tới R1?"
        />
        <button className="btn chat-send-btn" onClick={send} disabled={loading || !input.trim()}>
          <Send size={16} />
        </button>
      </div>
    </div>
  )
}
