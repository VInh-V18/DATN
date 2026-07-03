"""Ghi nhật ký suy luận (audit trail) dùng chung cho các adapter DB của agent_core.

Cả `app.agent.self_healing` và `app.security.playbook` cần ghi lại từng bước
quan sát/hành động của agent vào bảng `agent_traces` và phát sự kiện WebSocket
tương ứng - hàm này tránh lặp lại logic đó ở hai nơi.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.events import emit
from app.models.models import AgentTrace, TraceSubjectType


def record_trace(
    db: Session,
    subject_type: TraceSubjectType,
    subject_id: str,
    tool: str,
    arguments: dict[str, Any],
    result: Any,
    read_only: bool,
) -> None:
    db.add(
        AgentTrace(
            subject_type=subject_type,
            subject_id=subject_id,
            tool=tool,
            read_only=read_only,
            parameters=arguments,
            result=result if isinstance(result, dict) else {"output": str(result)},
        )
    )
    db.commit()
    emit(
        "agent_trace_added",
        {"subject_type": subject_type.value, "subject_id": subject_id, "tool": tool, "read_only": read_only},
    )
