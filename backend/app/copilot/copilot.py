"""Lớp Copilot hội thoại - mục 3.3.3.

Kỹ sư hỏi đáp bằng tiếng Việt; agent tự do gọi các tool chỉ đọc để tổng hợp câu
trả lời. Nếu cần đề xuất một hành động làm thay đổi cấu hình, agent chỉ ĐỀ XUẤT
(pending_action) - hành động chỉ thực sự chạy sau khi kỹ sư xác nhận qua
confirm_pending_action(), đúng tinh thần "tách bạch đọc và ghi" trong đề cương.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.llm.client import LLMClient
from app.models.models import ChatMessage, ChatSession
from app.tools.executor import ToolExecutor
from app.tools.specs import TOOL_SPEC_BY_NAME, TOOL_SPECS

SYSTEM_PROMPT = (
    "Bạn là Copilot mạng, một trợ lý hội thoại tiếng Việt cho kỹ sư vận hành. "
    "Bạn có thể tự do gọi các tool chỉ đọc (get_topology, get_node_status, get_interfaces, "
    "read_logs, get_metrics, get_routing_table, ping_test, detect_anomaly, map_attack) để trả lời. "
    "Nếu kỹ sư muốn thay đổi cấu hình hệ thống, bạn chỉ được ĐỀ XUẤT bằng cách gọi đúng một tool "
    "thay đổi hệ thống (send_command, push_config, start_node, stop_node, block_ip, isolate_node, "
    "rollback) - hành động này sẽ KHÔNG được thực thi ngay mà chờ kỹ sư xác nhận."
)

CONFIRMATION_PATTERN = re.compile(r"\b(có|đồng ý|xác nhận|thực hiện|thực thi|yes|ok|oke|đúng vậy)\b", re.IGNORECASE)

MAX_REACT_STEPS = 6


@dataclass
class CopilotReply:
    text: str
    requires_confirmation: bool
    pending_action: dict[str, Any] | None
    tool_calls: list[dict[str, Any]]


class Copilot:
    def __init__(self, db: Session, executor: ToolExecutor, llm: LLMClient) -> None:
        self.db = db
        self.executor = executor
        self.llm = llm

    def _history_messages(self, session: ChatSession) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in sorted(session.messages, key=lambda m: m.timestamp)[-20:]:
            role = "assistant" if msg.role == "assistant" else "user"
            messages.append({"role": role, "content": msg.content})
        return messages

    def ask(self, session: ChatSession, user_message: str) -> CopilotReply:
        self.db.add(ChatMessage(session_id=session.id, role="user", content=user_message))
        self.db.commit()

        if session.pending_action and CONFIRMATION_PATTERN.search(user_message):
            return self._confirm_pending_action(session)

        messages = self._history_messages(session)
        called_tools: list[dict[str, Any]] = []

        for _ in range(MAX_REACT_STEPS):
            result = self.llm.chat(messages, tools=TOOL_SPECS)
            if not result.tool_calls:
                self._save_assistant_reply(session, result.content)
                return CopilotReply(
                    text=result.content, requires_confirmation=False, pending_action=None, tool_calls=called_tools
                )

            state_changing_call = next(
                (c for c in result.tool_calls if not TOOL_SPEC_BY_NAME[c.name].read_only), None
            )
            if state_changing_call is not None:
                session.pending_action = {"tool": state_changing_call.name, "arguments": state_changing_call.arguments}
                self.db.commit()
                reply_text = result.content or (
                    f"Tôi đề xuất thực hiện '{state_changing_call.name}' với tham số "
                    f"{state_changing_call.arguments}. Bạn có xác nhận thực hiện không?"
                )
                self._save_assistant_reply(session, reply_text)
                return CopilotReply(
                    text=reply_text,
                    requires_confirmation=True,
                    pending_action=session.pending_action,
                    tool_calls=called_tools,
                )

            messages.append({"role": "assistant", "content": result.content, "tool_calls": result.tool_calls})
            for call in result.tool_calls:
                tool_result = self.executor.execute(call.name, call.arguments)
                output = tool_result.output if tool_result.ok else {"error": tool_result.error}
                called_tools.append({"name": call.name, "arguments": call.arguments, "output": output})
                messages.append(self.llm.tool_result_message(call, output))

        fallback = "Xin lỗi, tôi cần thêm thông tin để trả lời câu hỏi này."
        self._save_assistant_reply(session, fallback)
        return CopilotReply(text=fallback, requires_confirmation=False, pending_action=None, tool_calls=called_tools)

    def _confirm_pending_action(self, session: ChatSession) -> CopilotReply:
        plan = session.pending_action
        assert plan is not None
        result = self.executor.execute(plan["tool"], plan["arguments"])
        session.pending_action = None
        self.db.commit()
        output = result.output if result.ok else {"error": result.error}
        reply_text = (
            f"Đã thực hiện '{plan['tool']}'. Kết quả: {output}"
            if result.ok
            else f"Thực hiện '{plan['tool']}' thất bại: {result.error}"
        )
        self._save_assistant_reply(session, reply_text)
        return CopilotReply(
            text=reply_text,
            requires_confirmation=False,
            pending_action=None,
            tool_calls=[{"name": plan["tool"], "arguments": plan["arguments"], "output": output}],
        )

    def _save_assistant_reply(self, session: ChatSession, content: str) -> None:
        self.db.add(ChatMessage(session_id=session.id, role="assistant", content=content))
        self.db.commit()
