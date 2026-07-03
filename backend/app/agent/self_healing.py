"""Adapter DB/GNS3 cho SelfHealingEngine (app.agent_core.self_healing).

Lõi suy luận (Observe-Think-Act-Verify-Rollback, guardrails) sống hoàn toàn
trong `app.agent_core` và không biết gì về SQLAlchemy/FastAPI. Module này chỉ
làm nhiệm vụ "nối dây": cài đặt hai cổng mà engine cần -
`ToolRunner` (qua `app.tools.runner.ExecutorToolRunner`) và `IncidentRecorder`
(`_SqlAlchemyIncidentRecorder` dưới đây, ghi action_logs/incidents vào
PostgreSQL và phát sự kiện WebSocket) - rồi giữ nguyên API công khai cũ
(`SelfHealingAgent(db, executor, llm).tu_khac_phuc(incident_id)`) để
`app/api/incidents.py` không cần thay đổi.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.agent_core.self_healing import IncidentView, RemediationOutcome, SelfHealingEngine
from app.automation.device_client import DeviceClient, DeviceCredentials
from app.core.agent_trace import record_trace
from app.core.config import get_settings
from app.core.events import emit
from app.llm.client import LLMClient
from app.models.models import ActionLog, Device, Incident, IncidentStatus, TraceSubjectType
from app.tools.executor import ToolExecutor
from app.tools.runner import ExecutorToolRunner

# Giữ nguyên tên để tương thích ngược cho các chỗ import trước đây.
RemediationResult = RemediationOutcome


class _SqlAlchemyIncidentRecorder:
    """Cài đặt IncidentRecorder bằng SQLAlchemy Session + Netmiko (mục 3.5)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def log_action(self, incident_id: str, tool: str, arguments: dict[str, Any], result: Any) -> None:
        self.db.add(
            ActionLog(
                incident_id=incident_id,
                tool=tool,
                parameters=arguments,
                result=result if isinstance(result, dict) else {"output": str(result)},
            )
        )
        self.db.commit()

    def log_trace(self, incident_id: str, tool: str, arguments: dict[str, Any], result: Any, read_only: bool) -> None:
        record_trace(self.db, TraceSubjectType.incident, incident_id, tool, arguments, result, read_only)

    def set_status(self, incident_id: str, status: str) -> None:
        incident = self.db.get(Incident, incident_id)
        assert incident is not None
        incident.status = IncidentStatus(status)
        self.db.commit()
        emit("incident_updated", {"incident_id": incident_id, "status": status})

    def set_pending_action(self, incident_id: str, plan: dict[str, Any] | None) -> None:
        incident = self.db.get(Incident, incident_id)
        assert incident is not None
        incident.pending_action = plan
        self.db.commit()

    def snapshot_device(self, node_id: str) -> str | None:
        device = self.db.get(Device, node_id)
        if device is None or not device.management_address:
            return None
        with DeviceClient(DeviceCredentials.for_device(device.management_address)) as dc:
            return dc.save_config_snapshot()

    def mark_resolved(self, incident_id: str) -> None:
        incident = self.db.get(Incident, incident_id)
        assert incident is not None
        incident.resolved_at = datetime.utcnow()
        self.db.commit()


class SelfHealingAgent:
    def __init__(self, db: Session, executor: ToolExecutor, llm: LLMClient, max_retries: int | None = None) -> None:
        self.db = db
        self._engine = SelfHealingEngine(
            llm=llm,
            tool_runner=ExecutorToolRunner(executor),
            recorder=_SqlAlchemyIncidentRecorder(db),
            max_retries=max_retries or get_settings().agent_max_retries,
        )

    def tu_khac_phuc(self, incident_id: str) -> RemediationOutcome:
        incident = self.db.get(Incident, incident_id)
        if incident is None:
            raise ValueError(f"Không tìm thấy sự cố {incident_id}")

        view = IncidentView(
            id=incident.id,
            description=incident.description,
            device_ids=list(incident.device_ids),
            pending_action=incident.pending_action,
        )
        return self._engine.tu_khac_phuc(view)
