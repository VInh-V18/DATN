"""Adapter DB/GNS3 cho SecurityAgent (app.agent_core.security_agent).

Playbook phản ứng an ninh - SOC/SOAR thu nhỏ (mục 2.7, 3.3.4, luồng Hình 3.7).
Lõi suy luận (LLM phân tích + đề xuất phản ứng, guardrail rủi ro cao) sống
trong `app.agent_core.security_agent.SecurityAgent`; module này chỉ cài đặt
cổng `SecurityAlertRecorder` bằng SQLAlchemy (ghi security_alerts/
attack_mappings, phát WebSocket) và giữ nguyên API công khai cũ
(`SecurityPlaybook(db, executor, llm).handle_detection(...)`) để
`app/security/syslog_listener.py` và `app/api/security.py` không cần đổi cấu trúc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.agent_core.security_agent import DetectionView, SecurityAgent
from app.core.agent_trace import record_trace
from app.core.events import emit
from app.llm.client import LLMClient
from app.models.models import AttackMapping, SecurityAlert, Severity, TraceSubjectType
from app.security.detection import DetectionResult
from app.tools.executor import ToolExecutor
from app.tools.runner import ExecutorToolRunner


@dataclass
class PlaybookResult:
    status: str  # "blocked" | "awaiting_approval" | "alert_only" | "response_failed"
    alert_id: str


class _SqlAlchemySecurityRecorder:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_alert(self, indicator: str, source_ip: str, severity: str, detail: dict[str, Any]) -> str:
        alert = SecurityAlert(
            source_ip=source_ip,
            attack_type=indicator,
            severity=Severity(severity),
            status="detected",
            details=detail,
        )
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        emit("security_alert_created", {"alert_id": alert.id, "attack_type": alert.attack_type})
        return alert.id

    def add_attack_mapping(self, alert_id: str, technique_id: str, technique_name: str, tactic: str) -> None:
        self.db.add(AttackMapping(alert_id=alert_id, technique_id=technique_id, technique_name=technique_name, tactic=tactic))
        self.db.commit()

    def set_status(self, alert_id: str, status: str) -> None:
        alert = self.db.get(SecurityAlert, alert_id)
        assert alert is not None
        alert.status = status
        self.db.commit()
        emit("security_alert_updated", {"alert_id": alert_id, "status": status})

    def set_pending_action(self, alert_id: str, plan: dict[str, Any] | None) -> None:
        alert = self.db.get(SecurityAlert, alert_id)
        assert alert is not None
        alert.details = {**(alert.details or {}), "pending_action": plan}
        self.db.commit()

    def log_trace(self, alert_id: str, tool: str, arguments: dict[str, Any], result: Any, read_only: bool) -> None:
        record_trace(self.db, TraceSubjectType.security_alert, alert_id, tool, arguments, result, read_only)


class SecurityPlaybook:
    def __init__(self, db: Session, executor: ToolExecutor, llm: LLMClient) -> None:
        self.db = db
        self._agent = SecurityAgent(llm=llm, tool_runner=ExecutorToolRunner(executor), recorder=_SqlAlchemySecurityRecorder(db))

    def handle_detection(
        self, detection: DetectionResult, edge_node_id: str | None = None, auto_approved: bool = False
    ) -> PlaybookResult:
        view = DetectionView(
            indicator=detection.indicator, source_ip=detection.source_ip, detail=detection.detail, edge_node_id=edge_node_id
        )
        outcome = self._agent.handle(view, auto_approved=auto_approved)
        return PlaybookResult(status=outcome.status, alert_id=outcome.alert_id)

    def approve_and_execute(self, alert: SecurityAlert) -> PlaybookResult:
        pending = (alert.details or {}).get("pending_action")
        if not pending:
            return PlaybookResult(status="alert_only", alert_id=alert.id)
        outcome = self._agent.approve(alert.id, pending)
        return PlaybookResult(status=outcome.status, alert_id=outcome.alert_id)
