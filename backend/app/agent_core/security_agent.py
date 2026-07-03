"""SecurityAgent - lớp An ninh/SOC thu nhỏ (mục 2.7, 3.3.4), thuần logic.

Trước đây phản ứng an ninh hoàn toàn rule-based (chỉ tra bảng ánh xạ tĩnh:
"syn_flood -> isolate_node, còn lại -> block_ip"), bỏ qua đúng pha "Think" mà
đề cương mô tả ở luồng an ninh (Hình 3.7 - bước 3): "LLM phân tích nhật ký
liên quan và xác nhận đây là hành vi quét cổng". SecurityAgent lấp khoảng
trống đó: nhận một dấu hiệu đã được phát hiện theo luật ngưỡng (từ
`app.security.detection.SecurityDetectionEngine`), rồi cho LLM tự do đọc thêm
log/trạng thái thiết bị và tự quyết định hành động phản ứng phù hợp (thay vì
tra bảng tĩnh) - vẫn qua đúng vòng lặp ReAct dùng chung và guardrail rủi ro
cao/phê duyệt giống lớp Tự khắc phục.

Không phụ thuộc SQLAlchemy/FastAPI - xem `app.security.playbook.SecurityPlaybook`
là adapter DB/GNS3 mỏng bọc engine này.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.agent_core.react import run_react
from app.agent_core.types import Plan, ToolRunner
from app.llm.client import LLMClient
from app.tools.specs import TOOL_SPEC_BY_NAME, TOOL_SPECS

SYSTEM_PROMPT = (
    "Bạn là AI Agent an ninh mạng, hoạt động như một SOC/SOAR thu nhỏ. Bạn nhận được "
    "một dấu hiệu tấn công đã được một luật ngưỡng (rule-based) phát hiện trước; "
    "nhiệm vụ của bạn là phân tích thêm ngữ cảnh (đọc log qua read_logs, tra cứu ánh "
    "xạ MITRE ATT&CK qua map_attack, kiểm tra trạng thái thiết bị) để xác nhận mức độ "
    "nghiêm trọng, sau đó đề xuất ĐÚNG MỘT hành động phản ứng bằng cách gọi tool "
    "block_ip (chặn địa chỉ IP nguồn trên thiết bị biên) hoặc isolate_node (cô lập "
    "thiết bị bằng cách tắt toàn bộ cổng - chỉ dùng khi mối đe dọa nghiêm trọng, ví dụ "
    "DoS/SYN flood). Dùng đúng node_id thiết bị biên và địa chỉ IP nguồn đã cho."
)

MAX_THINK_STEPS = 5
DEFAULT_SEVERITY = "medium"

SEVERITY_BY_INDICATOR: dict[str, str] = {
    "port_scan": "medium",
    "syn_flood": "high",
    "ssh_bruteforce": "high",
}


@dataclass
class DetectionView:
    """Một dấu hiệu tấn công đã được phát hiện theo luật - đầu vào của SecurityAgent."""

    indicator: str
    source_ip: str
    detail: dict[str, Any]
    edge_node_id: str | None = None


@dataclass
class SecurityOutcome:
    status: str  # "blocked" | "awaiting_approval" | "alert_only" | "response_failed"
    detail: str
    alert_id: str


class SecurityAlertRecorder(Protocol):
    """Cổng ghi nhận cảnh báo an ninh + ánh xạ ATT&CK (mục 3.5, bảng security_alerts/attack_mappings)."""

    def create_alert(self, indicator: str, source_ip: str, severity: str, detail: dict[str, Any]) -> str:
        """Tạo bản ghi cảnh báo, trả về alert_id."""
        ...

    def add_attack_mapping(self, alert_id: str, technique_id: str, technique_name: str, tactic: str) -> None: ...
    def set_status(self, alert_id: str, status: str) -> None: ...
    def set_pending_action(self, alert_id: str, plan: dict[str, Any] | None) -> None: ...


class SecurityAgent:
    def __init__(self, llm: LLMClient, tool_runner: ToolRunner, recorder: SecurityAlertRecorder) -> None:
        self.llm = llm
        self.tool_runner = tool_runner
        self.recorder = recorder

    # --- Think: LLM phân tích và xác nhận (Hình 3.7, bước 3) ---

    def think(self, detection: DetectionView) -> Plan | None:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Dấu hiệu phát hiện: {detection.indicator}\n"
                    f"Địa chỉ IP nguồn: {detection.source_ip}\n"
                    f"Chi tiết luật đã kích hoạt: {detection.detail}\n"
                    f"Thiết bị biên có thể dùng để phản ứng (node_id): "
                    f"{detection.edge_node_id or 'không có - chỉ có thể ghi nhận cảnh báo'}"
                ),
            },
        ]
        result = run_react(self.llm, self.tool_runner, messages, TOOL_SPECS, MAX_THINK_STEPS)
        return result.plan

    # --- Vòng xử lý chính: ghi nhận -> ánh xạ ATT&CK -> think -> guardrail -> act ---

    def handle(self, detection: DetectionView, auto_approved: bool = False) -> SecurityOutcome:
        from app.security.attack_mapping import map_indicators

        severity = SEVERITY_BY_INDICATOR.get(detection.indicator, DEFAULT_SEVERITY)
        alert_id = self.recorder.create_alert(detection.indicator, detection.source_ip, severity, detection.detail)

        for mapping in map_indicators([detection.indicator]):
            self.recorder.add_attack_mapping(alert_id, mapping["technique_id"], mapping["technique_name"], mapping["tactic"])

        if detection.edge_node_id is None:
            self.recorder.set_status(alert_id, "alert_only")
            return SecurityOutcome(status="alert_only", detail="Không có thiết bị biên để phản ứng", alert_id=alert_id)

        plan = self.think(detection)
        if plan is None:
            self.recorder.set_status(alert_id, "alert_only")
            return SecurityOutcome(status="alert_only", detail="LLM không đề xuất hành động phản ứng cụ thể", alert_id=alert_id)

        if plan.tool not in TOOL_SPEC_BY_NAME:
            self.recorder.set_status(alert_id, "alert_only")
            return SecurityOutcome(status="alert_only", detail=f"Tool '{plan.tool}' không hợp lệ", alert_id=alert_id)

        risk = TOOL_SPEC_BY_NAME[plan.tool].risk
        if risk == "high" and not auto_approved:
            self.recorder.set_pending_action(alert_id, {"tool": plan.tool, "arguments": plan.arguments})
            self.recorder.set_status(alert_id, "awaiting_approval")
            return SecurityOutcome(status="awaiting_approval", detail=plan.rationale, alert_id=alert_id)

        return self._execute(alert_id, plan.tool, plan.arguments, plan.rationale)

    def approve(self, alert_id: str, pending_action: dict[str, Any]) -> SecurityOutcome:
        return self._execute(alert_id, pending_action["tool"], pending_action["arguments"], "")

    def _execute(self, alert_id: str, tool: str, arguments: dict[str, Any], detail: str) -> SecurityOutcome:
        result = self.tool_runner.run(tool, arguments)
        status = "blocked" if result.ok else "response_failed"
        self.recorder.set_status(alert_id, status)
        return SecurityOutcome(status=status, detail=detail or (result.error or ""), alert_id=alert_id)
