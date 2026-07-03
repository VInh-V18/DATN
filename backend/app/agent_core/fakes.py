"""Cài đặt giả lập của các cổng trong app.agent_core - dùng cho unit test và
`scripts/demo_agent.py`, KHÔNG cần API key (Ollama/Claude) hay GNS3/PostgreSQL
thật. Đây chính là điểm mấu chốt của việc tách lõi agent khỏi FastAPI/DB: toàn
bộ cơ chế Observe-Think-Act-Verify-Rollback, ReAct và guardrails có thể được
chứng minh hoạt động đúng chỉ bằng Python thuần.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.agent_core.types import ToolOutcome
from app.agent_core.self_healing import IncidentRecorder
from app.agent_core.security_agent import SecurityAlertRecorder
from app.llm.client import ChatResult, LLMClient, ToolCall


# --- LLM giả lập: phát lại một kịch bản cố định, không suy luận thật ---


@dataclass
class ScriptedStep:
    """Một lượt phản hồi giả lập: văn bản và/hoặc các tool cần gọi."""

    content: str = ""
    tool_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)


class FakeLLMClient(LLMClient):
    """Phát lại đúng kịch bản `script` theo thứ tự mỗi khi `.chat()` được gọi,
    bất kể nội dung `messages` truyền vào - đủ để lái vòng lặp ReAct/Self-
    Healing/Copilot đi qua các nhánh cần kiểm chứng (guardrail, verify,
    rollback, phê duyệt...) một cách xác định (deterministic)."""

    def __init__(self, script: list[ScriptedStep]) -> None:
        self._script = list(script)
        self._step_index = 0
        self.chat_calls: list[list[dict]] = []

    def chat(self, messages: list[dict[str, Any]], tools=None) -> ChatResult:
        self.chat_calls.append(list(messages))
        if self._step_index >= len(self._script):
            step = ScriptedStep(content="(hết kịch bản) không còn hành động nào để đề xuất.")
        else:
            step = self._script[self._step_index]
        self._step_index += 1

        tool_calls = [
            ToolCall(id=f"fake-{self._step_index}-{i}", name=name, arguments=args)
            for i, (name, args) in enumerate(step.tool_calls)
        ]
        return ChatResult(content=step.content, tool_calls=tool_calls)

    def tool_result_message(self, tool_call: ToolCall, output: Any) -> dict[str, Any]:
        return {"role": "tool", "content": json.dumps(output, ensure_ascii=False, default=str)}


# --- Tool runner giả lập: một "mạng" tối giản trong bộ nhớ ---


@dataclass
class FakeInterface:
    name: str
    status: str = "up"


@dataclass
class FakeDevice:
    id: str
    interfaces: dict[str, FakeInterface] = field(default_factory=dict)


class FakeToolRunner:
    """Giả lập các tool trong Bảng 3.3 trên một tập thiết bị trong bộ nhớ.

    Đủ để minh hoạ kịch bản KB01 (Bảng 5.2): một cổng bị shutdown khiến mất
    kết nối, agent chẩn đoán, gửi 'no shutdown', rồi kiểm chứng lại bằng ping.
    """

    def __init__(self, devices: dict[str, FakeDevice]) -> None:
        self.devices = devices
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        self.calls.append((name, dict(arguments)))
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return ToolOutcome(name=name, arguments=arguments, output=None, ok=False, error=f"Tool giả lập chưa hỗ trợ '{name}'")
        try:
            output = handler(**arguments)
            return ToolOutcome(name=name, arguments=arguments, output=output, ok=True)
        except Exception as exc:  # để guardrail/luồng lỗi trong engine cũng được test
            return ToolOutcome(name=name, arguments=arguments, output=None, ok=False, error=str(exc))

    def _all_up(self) -> bool:
        return all(iface.status == "up" for device in self.devices.values() for iface in device.interfaces.values())

    def _tool_get_node_status(self, node_id: str) -> dict:
        device = self.devices[node_id]
        return {"status": "started", "interfaces": [{"name": i.name, "status": i.status} for i in device.interfaces.values()]}

    def _tool_get_interfaces(self, node_id: str) -> list[dict]:
        device = self.devices[node_id]
        return [{"name": i.name, "status": i.status, "ip_address": None} for i in device.interfaces.values()]

    def _tool_read_logs(self, node_id: str, lines: int = 50) -> str:
        return "%LINK-3-UPDOWN: Interface changed state to down (giả lập)"

    def _tool_get_routing_table(self, node_id: str) -> str:
        return "O   10.0.0.0/24 [110/2] via 10.0.0.1 (giả lập)"

    def _tool_get_topology(self, project_id: str | None = None) -> dict:
        return {"nodes": list(self.devices.keys()), "links": []}

    def _tool_get_metrics(self, node_id: str, time_range: str = "-15m") -> list:
        return []

    def _tool_detect_anomaly(self, series: list[list[float]]) -> dict:
        return {"is_anomaly": False, "score": 0.0}

    def _tool_map_attack(self, indicators: list[str]) -> list[dict]:
        from app.security.attack_mapping import map_indicators

        return map_indicators(indicators)

    def _tool_send_command(self, node_id: str, command: str) -> str:
        return f"(giả lập) đã chạy lệnh '{command}' trên {node_id}"

    def _tool_push_config(self, node_id: str, config_lines: list[str]) -> str:
        for line in config_lines:
            if line.strip().lower() == "no shutdown":
                for iface in self.devices[node_id].interfaces.values():
                    if iface.status == "down":
                        iface.status = "up"
        return f"(giả lập) đã áp {len(config_lines)} dòng cấu hình lên {node_id}"

    def _tool_ping_test(self, source_node_id: str, target_node_id: str) -> dict:
        ok = self._all_up()
        return {"success_rate": 1.0 if ok else 0.0, "rtt_avg_ms": 4.2 if ok else None}

    def _tool_rollback(self, node_id: str, snapshot: str) -> str:
        return f"(giả lập) đã khôi phục cấu hình cho {node_id} từ {snapshot}"

    def _tool_start_node(self, node_id: str) -> str:
        return f"(giả lập) đã khởi động {node_id}"

    def _tool_stop_node(self, node_id: str) -> str:
        return f"(giả lập) đã dừng {node_id}"

    def _tool_block_ip(self, node_id: str, ip_address: str) -> str:
        return f"(giả lập) đã chặn IP {ip_address} trên {node_id}"

    def _tool_isolate_node(self, node_id: str) -> str:
        for iface in self.devices[node_id].interfaces.values():
            iface.status = "down"
        return f"(giả lập) đã cô lập {node_id}"


# --- Recorder giả lập: lưu trạng thái sự cố trong bộ nhớ thay vì PostgreSQL ---


class InMemoryIncidentRecorder(IncidentRecorder):
    def __init__(self) -> None:
        self.status: dict[str, str] = {}
        self.pending_action: dict[str, dict[str, Any] | None] = {}
        self.actions: list[tuple[str, str, dict, Any]] = []
        self.traces: list[tuple[str, str, dict, Any, bool]] = []
        self.resolved: set[str] = set()
        self.events: list[tuple[str, str]] = []

    def log_action(self, incident_id: str, tool: str, arguments: dict[str, Any], result: Any) -> None:
        self.actions.append((incident_id, tool, arguments, result))

    def log_trace(self, incident_id: str, tool: str, arguments: dict[str, Any], result: Any, read_only: bool) -> None:
        self.traces.append((incident_id, tool, arguments, result, read_only))

    def set_status(self, incident_id: str, status: str) -> None:
        self.status[incident_id] = status
        self.events.append((incident_id, status))

    def set_pending_action(self, incident_id: str, plan: dict[str, Any] | None) -> None:
        self.pending_action[incident_id] = plan

    def snapshot_device(self, node_id: str) -> str | None:
        return f"snapshot::{node_id}"

    def mark_resolved(self, incident_id: str) -> None:
        self.resolved.add(incident_id)


class InMemorySecurityRecorder(SecurityAlertRecorder):
    def __init__(self) -> None:
        self._counter = 0
        self.alerts: dict[str, dict[str, Any]] = {}
        self.attack_mappings: dict[str, list[dict[str, str]]] = {}
        self.pending_action: dict[str, dict[str, Any] | None] = {}
        self.traces: list[tuple[str, str, dict, Any, bool]] = []

    def create_alert(self, indicator: str, source_ip: str, severity: str, detail: dict[str, Any]) -> str:
        self._counter += 1
        alert_id = f"alert-{self._counter}"
        self.alerts[alert_id] = {
            "indicator": indicator,
            "source_ip": source_ip,
            "severity": severity,
            "detail": detail,
            "status": "detected",
        }
        self.attack_mappings[alert_id] = []
        return alert_id

    def add_attack_mapping(self, alert_id: str, technique_id: str, technique_name: str, tactic: str) -> None:
        self.attack_mappings[alert_id].append({"technique_id": technique_id, "technique_name": technique_name, "tactic": tactic})

    def set_status(self, alert_id: str, status: str) -> None:
        self.alerts[alert_id]["status"] = status

    def set_pending_action(self, alert_id: str, plan: dict[str, Any] | None) -> None:
        self.pending_action[alert_id] = plan

    def log_trace(self, alert_id: str, tool: str, arguments: dict[str, Any], result: Any, read_only: bool) -> None:
        self.traces.append((alert_id, tool, arguments, result, read_only))
