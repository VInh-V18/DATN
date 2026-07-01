import { useState } from 'react'
import { sendChatMessage } from '../api/client'
import type { ChatMessageTurn } from '../api/types'

export default function ChatPage() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessageTurn[]>([])
  const [input, setInput] = useState('')
  const [pendingConfirmation, setPendingConfirmation] = useState(false)
  const [loading, setLoading] = useState(false)

  const send = async () => {
    if (!input.trim()) return
    const userMessage = input
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }])
    setInput('')
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
    <div className="page chat-page">
      <h1>Copilot hội thoại</h1>
      <p className="hint">
        Hỏi đáp bằng tiếng Việt về trạng thái mạng. Các hành động thay đổi cấu hình sẽ cần bạn xác nhận
        trước khi thực thi.
      </p>
      <div className="chat-window">
        {messages.map((message, idx) => (
          <div key={idx} className={`chat-bubble chat-${message.role}`}>
            {message.content}
          </div>
        ))}
        {loading && <div className="chat-bubble chat-assistant">Đang suy nghĩ...</div>}
        {pendingConfirmation && (
          <div className="chat-bubble chat-system">
            Agent đang chờ bạn xác nhận hành động. Trả lời "có" để thực hiện hoặc "không" để hủy.
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
        <button onClick={send} disabled={loading}>
          Gửi
        </button>
      </div>
    </div>
  )
}
