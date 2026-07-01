"""Playbook phản ứng an ninh - SOC/SOAR thu nhỏ (mục 2.7, 3.3.4, luồng Hình 3.7).

Chuỗi hành động: ghi nhận cảnh báo -> ánh xạ ATT&CK -> (guardrail phê duyệt nếu
rủi ro cao) -> chặn IP nguồn / cô lập node -> kiểm chứng -> thông báo kỹ sư.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.events import emit
from app.models.models import AttackMapping, SecurityAlert, Severity
from app.security.attack_mapping import map_indicators
from app.security.detection import DetectionResult
from app.tools.executor import ToolExecutor
from app.tools.specs import TOOL_SPEC_BY_NAME

SEVERITY_BY_INDICATOR = {
    "port_scan": Severity.medium,
    "syn_flood": Severity.high,
    "ssh_bruteforce": Severity.high,
}


@dataclass
class PlaybookResult:
    status: str  # "blocked" | "awaiting_approval" | "alert_only"
    alert_id: str


class SecurityPlaybook:
    def __init__(self, db: Session, executor: ToolExecutor) -> None:
        self.db = db
        self.executor = executor

    def handle_detection(
        self, detection: DetectionResult, edge_node_id: str | None = None, auto_approved: bool = False
    ) -> PlaybookResult:
        alert = SecurityAlert(
            source_ip=detection.source_ip,
            attack_type=detection.indicator,
            severity=SEVERITY_BY_INDICATOR.get(detection.indicator, Severity.medium),
            status="detected",
            details=detection.detail,
        )
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)

        for mapping in map_indicators([detection.indicator]):
            self.db.add(
                AttackMapping(
                    alert_id=alert.id,
                    technique_id=mapping["technique_id"],
                    technique_name=mapping["technique_name"],
                    tactic=mapping["tactic"],
                )
            )
        self.db.commit()
        emit("security_alert_created", {"alert_id": alert.id, "attack_type": alert.attack_type})

        if edge_node_id is None:
            alert.status = "alert_only"
            self.db.commit()
            return PlaybookResult(status="alert_only", alert_id=alert.id)

        response_tool = "isolate_node" if detection.indicator == "syn_flood" else "block_ip"
        risk = TOOL_SPEC_BY_NAME[response_tool].risk

        if risk == "high" and not auto_approved:
            alert.status = "awaiting_approval"
            alert.details = {**alert.details, "pending_action": {"tool": response_tool, "node_id": edge_node_id}}
            self.db.commit()
            emit("security_alert_updated", {"alert_id": alert.id, "status": alert.status})
            return PlaybookResult(status="awaiting_approval", alert_id=alert.id)

        return self._execute_response(alert, response_tool, edge_node_id)

    def approve_and_execute(self, alert: SecurityAlert) -> PlaybookResult:
        pending = (alert.details or {}).get("pending_action")
        if not pending:
            return PlaybookResult(status="alert_only", alert_id=alert.id)
        return self._execute_response(alert, pending["tool"], pending["node_id"])

    def _execute_response(self, alert: SecurityAlert, tool: str, node_id: str) -> PlaybookResult:
        arguments = {"node_id": node_id}
        if tool == "block_ip":
            arguments["ip_address"] = alert.source_ip
        result = self.executor.execute(tool, arguments)
        alert.status = "blocked" if result.ok else "response_failed"
        self.db.commit()
        emit("security_alert_updated", {"alert_id": alert.id, "status": alert.status})
        return PlaybookResult(status=alert.status, alert_id=alert.id)
