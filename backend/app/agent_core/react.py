"""Vòng lặp ReAct dùng chung - Reasoning + Acting xen kẽ (mục 2.2, tham chiếu
Yao et al., 2023 "ReAct: Synergizing Reasoning and Acting in Language Models").

Cả lớp Tự khắc phục (app.agent_core.self_healing) lẫn Copilot
(app.agent_core.copilot) đều cần cùng một khuôn mẫu suy luận: cho LLM tự do
gọi các tool CHỈ ĐỌC để thu thập thêm ngữ cảnh, xen kẽ nhiều bước, cho đến khi
LLM hoặc (a) trả lời bằng văn bản thuần (không có hành động nào), hoặc
(b) đề xuất một tool THAY ĐỔI HỆ THỐNG - lúc đó vòng lặp dừng lại và trả về
`Plan` đó, KHÔNG tự ý thực thi (việc thực thi hành động thay đổi hệ thống là
trách nhiệm của tầng gọi, sau khi đã áp guardrails - xem self_healing.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agent_core.types import Plan, ToolRunner
from app.llm.client import LLMClient
from app.tools.specs import TOOL_SPEC_BY_NAME, ToolSpec


@dataclass
class ReActResult:
    plan: Plan | None
    final_text: str
    tool_calls: list[dict]


def run_react(
    llm: LLMClient,
    tool_runner: ToolRunner,
    messages: list[dict],
    tools: list[ToolSpec],
    max_steps: int,
) -> ReActResult:
    """Chạy tối đa `max_steps` bước Think; mỗi bước có thể đọc thêm dữ liệu.

    `messages` được truyền vào (và biến đổi tại chỗ) là lịch sử hội thoại đầy
    đủ, đã kết thúc bằng lượt hỏi/ngữ cảnh mới nhất - giống định dạng mà
    `LLMClient.chat()` mong đợi.
    """
    tool_calls_log: list[dict] = []

    for _ in range(max_steps):
        result = llm.chat(messages, tools=tools)

        if not result.tool_calls:
            return ReActResult(plan=None, final_text=result.content, tool_calls=tool_calls_log)

        action_call = _first_state_changing_call(result.tool_calls)
        if action_call is not None:
            return ReActResult(
                plan=Plan(
                    tool=action_call.name,
                    arguments=action_call.arguments,
                    node_id=action_call.arguments.get("node_id", ""),
                    rationale=result.content,
                ),
                final_text=result.content,
                tool_calls=tool_calls_log,
            )

        # Toàn bộ tool_calls ở bước này đều chỉ đọc: thực thi để lấy thêm ngữ
        # cảnh rồi tiếp tục suy luận (đúng tinh thần xen kẽ Reasoning-Acting).
        messages.append({"role": "assistant", "content": result.content, "tool_calls": result.tool_calls})
        for call in result.tool_calls:
            outcome = tool_runner.run(call.name, call.arguments)
            output = outcome.output if outcome.ok else {"error": outcome.error}
            tool_calls_log.append({"name": call.name, "arguments": call.arguments, "output": output})
            messages.append(llm.tool_result_message(call, output))

    return ReActResult(plan=None, final_text="", tool_calls=tool_calls_log)


def _first_state_changing_call(tool_calls):
    for call in tool_calls:
        spec = TOOL_SPEC_BY_NAME.get(call.name)
        if spec and not spec.read_only:
            return call
    return None
