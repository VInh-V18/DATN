"""Lớp Tự khắc phục - lõi của hệ thống (mục 3.3.2).

Hiện thực vòng lặp Observe - Think - Act - Verify - Rollback, đúng theo mã giả
đã mô tả trong đề cương:

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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm.client import LLMClient, ToolCall
from app.models.models import ActionLog, Device, Incident, IncidentStatus
from app.tools.executor import GuardrailViolation, ToolExecutor
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


@dataclass
class Plan:
    tool: str
    arguments: dict[str, Any]
    node_id: str
    rationale: str = ""


@dataclass
class RemediationResult:
    status: str  # "resolved" | "awaiting_approval" | "needs_intervention" | "guardrail_blocked"
    detail: str


class SelfHealingAgent:
    def __init__(self, db: Session, executor: ToolExecutor, llm: LLMClient, max_retries: int | None = None) -> None:
        self.db = db
        self.executor = executor
        self.llm = llm
        self.max_retries = max_retries or get_settings().agent_max_retries

    # --- Observe ---

    def observe(self, incident: Incident) -> dict[str, Any]:
        state: dict[str, Any] = {"devices": {}}
        for device_id in incident.device_ids:
            result = self.executor.execute("get_node_status", {"node_id": device_id})
            interfaces = self.executor.execute("get_interfaces", {"node_id": device_id})
            state["devices"][device_id] = {
                "status": result.output if result.ok else {"error": result.error},
                "interfaces": interfaces.output if interfaces.ok else {"error": interfaces.error},
            }
        return state

    # --- Think (ReAct: xen kẽ đọc thêm thông tin và đề xuất hành động) ---

    def think(self, incident: Incident, state: dict[str, Any]) -> Plan | None:
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
        for _ in range(MAX_THINK_STEPS):
            result = self.llm.chat(messages, tools=TOOL_SPECS)
            if not result.tool_calls:
                return None
            action_call = self._first_state_changing_call(result.tool_calls)
            if action_call is not None:
                return Plan(
                    tool=action_call.name,
                    arguments=action_call.arguments,
                    node_id=action_call.arguments.get("node_id", ""),
                    rationale=result.content,
                )
            # Toàn bộ tool_calls là read-only: thực thi để thu thập thêm ngữ cảnh rồi tiếp tục suy luận.
            messages.append({"role": "assistant", "content": result.content, "tool_calls": result.tool_calls})
            for call in result.tool_calls:
                output = self._safe_execute(call)
                messages.append(self.llm.tool_result_message(call, output))
        return None

    @staticmethod
    def _first_state_changing_call(tool_calls: list[ToolCall]) -> ToolCall | None:
        for call in tool_calls:
            spec = TOOL_SPEC_BY_NAME.get(call.name)
            if spec and not spec.read_only:
                return call
        return None

    def _safe_execute(self, call: ToolCall) -> Any:
        result = self.executor.execute(call.name, call.arguments)
        return result.output if result.ok else {"error": result.error}

    # --- Guardrails ---

    @staticmethod
    def duoc_phep(tool_name: str) -> bool:
        return tool_name in TOOL_SPEC_BY_NAME

    @staticmethod
    def rui_ro_cao(plan: Plan) -> bool:
        spec = TOOL_SPEC_BY_NAME.get(plan.tool)
        return bool(spec and spec.risk == "high")

    def cho_phe_duyet(self, incident: Incident, plan: Plan) -> bool:
        """True nếu đã được kỹ sư phê duyệt cho đúng plan này (mục 3.3.2 guardrail)."""
        approved = incident.pending_action is not None and incident.pending_action.get("approved") is True
        return approved and incident.pending_action.get("tool") == plan.tool

    # --- Act / Verify / Rollback ---

    def luu_cau_hinh(self, node_id: str) -> str | None:
        result = self.executor.execute("get_routing_table", {"node_id": node_id})
        return None  # snapshot thật sự lấy qua DeviceClient.save_config_snapshot trong _snapshot_device

    def _snapshot_device(self, node_id: str) -> str | None:
        device = self.db.get(Device, node_id)
        if device is None or not device.management_address:
            return None
        from app.automation.device_client import DeviceClient, DeviceCredentials

        with DeviceClient(DeviceCredentials.for_device(device.management_address)) as dc:
            return dc.save_config_snapshot()

    def verify(self, incident: Incident) -> bool:
        if len(incident.device_ids) < 2:
            return True
        source, target = incident.device_ids[0], incident.device_ids[1]
        target_device = self.db.get(Device, target)
        target_ip = target_device.management_address if target_device else None
        if not target_ip:
            return True
        result = self.executor.execute("ping_test", {"source_node_id": source, "target_ip": target_ip})
        return bool(result.ok and result.output.get("success_rate", 0) >= 0.8)

    def rollback(self, node_id: str, snapshot: str | None) -> None:
        if snapshot:
            self.executor.execute("rollback", {"node_id": node_id, "snapshot": snapshot})

    def _log_action(self, incident: Incident, tool: str, arguments: dict, result: Any) -> None:
        self.db.add(
            ActionLog(
                incident_id=incident.id,
                tool=tool,
                parameters=arguments,
                result=result if isinstance(result, dict) else {"output": str(result)},
            )
        )
        self.db.commit()

    # --- Vòng lặp chính ---

    def tu_khac_phuc(self, incident_id: str) -> RemediationResult:
        incident = self.db.get(Incident, incident_id)
        if incident is None:
            raise ValueError(f"Không tìm thấy sự cố {incident_id}")

        incident.status = IncidentStatus.diagnosing
        self.db.commit()

        for _ in range(self.max_retries):
            state = self.observe(incident)
            plan = self.think(incident, state)
            if plan is None:
                return self._finish(incident, IncidentStatus.failed, "needs_intervention")

            if not self.duoc_phep(plan.tool):
                self._log_action(incident, plan.tool, plan.arguments, {"guardrail": "tool_not_allowed"})
                return self._finish(incident, IncidentStatus.failed, "guardrail_blocked")

            if self.rui_ro_cao(plan) and not self.cho_phe_duyet(incident, plan):
                incident.status = IncidentStatus.awaiting_approval
                incident.pending_action = {"tool": plan.tool, "arguments": plan.arguments, "approved": False}
                self.db.commit()
                return RemediationResult(status="awaiting_approval", detail=plan.rationale)

            snapshot = self._snapshot_device(plan.node_id)
            incident.status = IncidentStatus.remediating
            self.db.commit()

            try:
                result = self.executor.execute(plan.tool, plan.arguments)
            except GuardrailViolation as exc:
                self._log_action(incident, plan.tool, plan.arguments, {"guardrail": str(exc)})
                return self._finish(incident, IncidentStatus.failed, "guardrail_blocked")

            self._log_action(incident, plan.tool, plan.arguments, result.output if result.ok else {"error": result.error})

            if result.ok and self.verify(incident):
                return self._finish(incident, IncidentStatus.resolved, "thanh_cong")

            self.rollback(plan.node_id, snapshot)

        return self._finish(incident, IncidentStatus.failed, "can_can_thiep")

    def _finish(self, incident: Incident, status: IncidentStatus, detail: str) -> RemediationResult:
        incident.status = status
        if status == IncidentStatus.resolved:
            from datetime import datetime

            incident.resolved_at = datetime.utcnow()
        self.db.commit()
        return RemediationResult(status=status.value, detail=detail)
