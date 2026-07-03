"""Adapter DB cho CopilotEngine (app.agent_core.copilot).

Lõi hội thoại (ReAct, tách bạch đọc/ghi, mục 3.3.3) sống trong `app.agent_core`
và không biết gì về SQLAlchemy. Module này chỉ lo việc "nối dây": đọc/ghi lịch
sử hội thoại từ bảng `chat_sessions`/`chat_messages`, cài đặt cổng ToolRunner
qua `app.tools.runner.ExecutorToolRunner`, và quyết định gọi `engine.ask()`
hay `engine.confirm()` dựa trên `session.pending_action` - rồi giữ nguyên API
công khai cũ (`Copilot(db, executor, llm).ask(session, message)`) để
`app/api/chat.py` không cần thay đổi.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agent_core.copilot import CopilotEngine, CopilotTurn, SYSTEM_PROMPT, is_confirmation
from app.llm.client import LLMClient
from app.models.models import ChatMessage, ChatSession
from app.tools.executor import ToolExecutor
from app.tools.runner import ExecutorToolRunner

# Giữ nguyên tên để tương thích ngược cho các chỗ import trước đây.
CopilotReply = CopilotTurn


class Copilot:
    def __init__(self, db: Session, executor: ToolExecutor, llm: LLMClient) -> None:
        self.db = db
        self._engine = CopilotEngine(llm=llm, tool_runner=ExecutorToolRunner(executor))

    def _history_messages(self, session: ChatSession) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in sorted(session.messages, key=lambda m: m.timestamp)[-20:]:
            role = "assistant" if msg.role == "assistant" else "user"
            messages.append({"role": role, "content": msg.content})
        return messages

    def ask(self, session: ChatSession, user_message: str) -> CopilotTurn:
        self.db.add(ChatMessage(session_id=session.id, role="user", content=user_message))
        self.db.commit()

        if session.pending_action and is_confirmation(user_message):
            turn = self._engine.confirm(session.pending_action)
        else:
            messages = self._history_messages(session)  # đã gồm lượt hỏi vừa lưu ở trên
            turn = self._engine.ask(messages)

        session.pending_action = turn.pending_action
        self.db.commit()
        self._save_assistant_reply(session, turn.text)
        return turn

    def _save_assistant_reply(self, session: ChatSession, content: str) -> None:
        self.db.add(ChatMessage(session_id=session.id, role="assistant", content=content))
        self.db.commit()
