"""Self-Healing Engine - lõi của hệ thống (mục 3.3.2), thuần logic.

Hiện thực vòng lặp Observe - Think - Act - Verify - Rollback đúng theo mã giả
trong đề cương:

    def tu_khac_phuc(su_co):
        for lan_thu in range(SO_LAN_THU_TOI_DA):
            trang_thai = observe(su_co)
            ke_hoach   = llm_chan_doan(trang_thai)
            if not duoc_phep(ke_hoach.tool): ...
            if rui_ro_cao(ke_hoach) and not cho_phe_duyet(ke_hoach): ...
            snapshot = luu_cau_hinh(ke_hoach.thiet_bi)
            execute(ke_hoach)
            if verify(su_co): return thanh_cong
            rollback(snapshot)
        return can_can_thiep

Không phụ thuộc SQLAlchemy/FastAPI: mọi tương tác với hệ thống thật (chạy
tool, ghi log, lưu/khôi phục cấu hình, cập nhật trạng thái sự cố) đi qua hai
cổng (Protocol) - `ToolRunner` và `IncidentRecorder` - để engine có thể chạy
hoàn toàn trong bộ nhớ (unit test, demo) hoặc gắn với PostgreSQL + GNS3 thật
(xem `app.agent.self_healing.SelfHealingAgent`, lớp adapter mỏng bọc engine
này) mà không cần sửa logic suy luận.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.agent_core.react import ReActResult, run_react
from app.agent_core.types import Plan, ToolRunner
from app.llm.client import LLMClient
from app.tools.specs import TOOL_SPEC_BY_NAME, TOOL_SPECS

SYSTEM_PROMPT = (
    "Bạn là AI Agent vận hành mạng, hoạt động theo vòng lặp Observe-Think-Act. "
    "Nhiệm vụ của bạn là chẩn đoán nguyên nhân gốc của sự cố mạng và đề xuất MỘT hành động "
    "khắc phục bằng cách gọi đúng một tool thay đổi cấu hình (start_node, stop_node, send_command, "
    "push_config, rollback). Trước khi đề xuất hành động, bạn có thể gọi các tool chỉ đọc "
    "(get_topology, get_node_status, get_interfaces, read_logs, get_metrics, get_routing_table) "
    "để thu thập thêm thông tin. Chỉ đề xuất đúng một hành động thay đổi hệ thống mỗi lượt."
)

MAX_THINK_STEPS = 6
DEFAULT_MAX_RETRIES = 3


@dataclass
class IncidentView:
    """Ảnh chụp trạng thái sự cố mà engine cần để suy luận - không phải ORM model."""

    id: str
    description: str
    device_ids: list[str]
    pending_action: dict[str, Any] | None = None


@dataclass
class RemediationOutcome:
    status: str  # "resolved" | "awaiting_approval" | "needs_intervention" | "guardrail_blocked"
    detail: str


class IncidentRecorder(Protocol):
    """Cổng ghi nhận tác dụng phụ (persistence + thông báo) của vòng lặp.

    Cài đặt thật: `app.agent._adapters.SqlAlchemyIncidentRecorder` (ghi
    action_logs/incidents vào PostgreSQL và phát WebSocket). Cài đặt giả lập:
    `app.agent_core.fakes.InMemoryIncidentRecorder`.
    """

    def log_action(self, incident_id: str, tool: str, arguments: dict[str, Any], result: Any) -> None: ...
    def log_trace(self, incident_id: str, tool: str, arguments: dict[str, Any], result: Any, read_only: bool) -> None:
        """Ghi một bước quan sát/suy luận (Think) - audit trail đầy đủ, mục 3.1."""
        ...

    def set_status(self, incident_id: str, status: str) -> None: ...
    def set_pending_action(self, incident_id: str, plan: dict[str, Any] | None) -> None: ...
    def snapshot_device(self, node_id: str) -> str | None: ...
    def mark_resolved(self, incident_id: str) -> None: ...


class SelfHealingEngine:
    def __init__(
        self,
        llm: LLMClient,
        tool_runner: ToolRunner,
        recorder: IncidentRecorder,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.llm = llm
        self.tool_runner = tool_runner
        self.recorder = recorder
        self.max_retries = max_retries

    # --- Observe ---

    def observe(self, incident: IncidentView) -> dict[str, Any]:
        state: dict[str, Any] = {"devices": {}}
        for device_id in incident.device_ids:
            status = self.tool_runner.run("get_node_status", {"node_id": device_id})
            interfaces = self.tool_runner.run("get_interfaces", {"node_id": device_id})
            state["devices"][device_id] = {
                "status": status.output if status.ok else {"error": status.error},
                "interfaces": interfaces.output if interfaces.ok else {"error": interfaces.error},
            }
        return state

    # --- Think (ReAct) ---

    def think(self, incident: IncidentView, state: dict[str, Any]) -> ReActResult:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Sự cố: {incident.description}\n"
                    f"Các thiết bị liên quan: {incident.device_ids}\n"
                    f"Trạng thái quan sát được: {state}"
                ),
            },
        ]
        return run_react(self.llm, self.tool_runner, messages, TOOL_SPECS, MAX_THINK_STEPS)

    # --- Guardrails (mục 3.3.2) ---

    @staticmethod
    def duoc_phep(tool_name: str) -> bool:
        return tool_name in TOOL_SPEC_BY_NAME

    @staticmethod
    def rui_ro_cao(plan: Plan) -> bool:
        spec = TOOL_SPEC_BY_NAME.get(plan.tool)
        return bool(spec and spec.risk == "high")

    @staticmethod
    def cho_phe_duyet(incident: IncidentView, plan: Plan) -> bool:
        pending = incident.pending_action
        approved = pending is not None and pending.get("approved") is True
        return approved and pending.get("tool") == plan.tool

    # --- Verify / Rollback ---

    def verify(self, incident: IncidentView) -> bool:
        if len(incident.device_ids) < 2:
            return True
        source, target = incident.device_ids[0], incident.device_ids[1]
        result = self.tool_runner.run("ping_test", {"source_node_id": source, "target_node_id": target})
        return bool(result.ok and result.output.get("success_rate", 0) >= 0.8)

    def rollback(self, node_id: str, snapshot: str | None) -> None:
        if snapshot:
            self.tool_runner.run("rollback", {"node_id": node_id, "snapshot": snapshot})

    # --- Vòng lặp chính ---

    def tu_khac_phuc(self, incident: IncidentView) -> RemediationOutcome:
        self.recorder.set_status(incident.id, "diagnosing")

        for _ in range(self.max_retries):
            state = self.observe(incident)
            react_result = self.think(incident, state)
            for call in react_result.tool_calls:
                self.recorder.log_trace(incident.id, call["name"], call["arguments"], call["output"], True)

            plan = react_result.plan
            if plan is None:
                return self._finish(incident.id, "failed", "needs_intervention")

            if not self.duoc_phep(plan.tool):
                blocked_result = {"guardrail": "tool_not_allowed"}
                self.recorder.log_action(incident.id, plan.tool, plan.arguments, blocked_result)
                self.recorder.log_trace(incident.id, plan.tool, plan.arguments, blocked_result, False)
                return self._finish(incident.id, "failed", "guardrail_blocked")

            if self.rui_ro_cao(plan) and not self.cho_phe_duyet(incident, plan):
                self.recorder.log_trace(
                    incident.id, plan.tool, plan.arguments, {"proposed": True, "awaiting_approval": True}, False
                )
                self.recorder.set_pending_action(
                    incident.id, {"tool": plan.tool, "arguments": plan.arguments, "approved": False}
                )
                self.recorder.set_status(incident.id, "awaiting_approval")
                return RemediationOutcome(status="awaiting_approval", detail=plan.rationale)

            snapshot = self.recorder.snapshot_device(plan.node_id)
            self.recorder.set_status(incident.id, "remediating")

            result = self.tool_runner.run(plan.tool, plan.arguments)
            action_result = result.output if result.ok else {"error": result.error}
            self.recorder.log_action(incident.id, plan.tool, plan.arguments, action_result)
            self.recorder.log_trace(incident.id, plan.tool, plan.arguments, action_result, False)

            if result.ok and self.verify(incident):
                return self._finish(incident.id, "resolved", "thanh_cong")

            self.rollback(plan.node_id, snapshot)

        return self._finish(incident.id, "failed", "can_can_thiep")

    def _finish(self, incident_id: str, status: str, detail: str) -> RemediationOutcome:
        self.recorder.set_status(incident_id, status)
        if status == "resolved":
            self.recorder.mark_resolved(incident_id)
        return RemediationOutcome(status=status, detail=detail)
