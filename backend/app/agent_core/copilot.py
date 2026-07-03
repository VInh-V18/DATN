"""Copilot Engine - trợ lý hội thoại (mục 3.3.3), thuần logic.

Tách bạch hành động đọc (tự do) và hành động ghi (cần xác nhận): agent tự do
gọi các tool chỉ đọc để tổng hợp câu trả lời; nếu cần đề xuất một hành động
làm thay đổi cấu hình, engine chỉ trả về `pending_action` - KHÔNG tự thực thi.
Việc thực thi chỉ diễn ra ở lượt hỏi tiếp theo, khi kỹ sư xác nhận (câu trả
lời khớp `CONFIRMATION_PATTERN`), qua `CopilotEngine.confirm()`.

Không phụ thuộc SQLAlchemy/FastAPI: lịch sử hội thoại và việc lưu trữ lâu dài
do lớp gọi đảm nhiệm (xem `app.copilot.copilot.Copilot`, adapter mỏng bọc
engine này bằng ChatSession/ChatMessage).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.agent_core.types import ToolRunner
from app.llm.client import LLMClient
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

# Bắt các câu trả lời phủ định trước - tránh khớp nhầm "đồng ý" bên trong
# "không đồng ý" thành một xác nhận đồng ý.
NEGATION_PATTERN = re.compile(r"\b(không|đừng|chưa|hủy|huỷ|từ chối|no)\b", re.IGNORECASE)

MAX_REACT_STEPS = 6


@dataclass
class CopilotTurn:
    text: str
    requires_confirmation: bool
    pending_action: dict[str, Any] | None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


def is_confirmation(message: str) -> bool:
    if NEGATION_PATTERN.search(message):
        return False
    return bool(CONFIRMATION_PATTERN.search(message))


class CopilotEngine:
    def __init__(self, llm: LLMClient, tool_runner: ToolRunner) -> None:
        self.llm = llm
        self.tool_runner = tool_runner

    def ask(self, messages: list[dict[str, str]]) -> CopilotTurn:
        """`messages` là lịch sử hội thoại đầy đủ (đã gồm system prompt do lớp
        gọi thêm vào, xem `app.copilot.copilot.Copilot._history_messages`),
        kết thúc bằng lượt hỏi mới nhất của kỹ sư."""
        called_tools: list[dict[str, Any]] = []

        for _ in range(MAX_REACT_STEPS):
            result = self.llm.chat(messages, tools=TOOL_SPECS)
            if not result.tool_calls:
                return CopilotTurn(text=result.content, requires_confirmation=False, pending_action=None, tool_calls=called_tools)

            state_changing_call = next(
                (c for c in result.tool_calls if not TOOL_SPEC_BY_NAME[c.name].read_only), None
            )
            if state_changing_call is not None:
                pending_action = {"tool": state_changing_call.name, "arguments": state_changing_call.arguments}
                reply_text = result.content or (
                    f"Tôi đề xuất thực hiện '{state_changing_call.name}' với tham số "
                    f"{state_changing_call.arguments}. Bạn có xác nhận thực hiện không?"
                )
                return CopilotTurn(
                    text=reply_text, requires_confirmation=True, pending_action=pending_action, tool_calls=called_tools
                )

            messages.append({"role": "assistant", "content": result.content, "tool_calls": result.tool_calls})
            for call in result.tool_calls:
                outcome = self.tool_runner.run(call.name, call.arguments)
                output = outcome.output if outcome.ok else {"error": outcome.error}
                called_tools.append({"name": call.name, "arguments": call.arguments, "output": output})
                messages.append(self.llm.tool_result_message(call, output))

        fallback = "Xin lỗi, tôi cần thêm thông tin để trả lời câu hỏi này."
        return CopilotTurn(text=fallback, requires_confirmation=False, pending_action=None, tool_calls=called_tools)

    def confirm(self, pending_action: dict[str, Any]) -> CopilotTurn:
        outcome = self.tool_runner.run(pending_action["tool"], pending_action["arguments"])
        output = outcome.output if outcome.ok else {"error": outcome.error}
        reply_text = (
            f"Đã thực hiện '{pending_action['tool']}'. Kết quả: {output}"
            if outcome.ok
            else f"Thực hiện '{pending_action['tool']}' thất bại: {outcome.error}"
        )
        return CopilotTurn(
            text=reply_text,
            requires_confirmation=False,
            pending_action=None,
            tool_calls=[{"name": pending_action["tool"], "arguments": pending_action["arguments"], "output": output}],
        )
