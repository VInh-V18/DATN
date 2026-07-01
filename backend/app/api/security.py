from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_tool_executor, require_approver
from app.core.database import get_db
from app.core.security import TokenPayload
from app.models.models import SecurityAlert
from app.schemas.schemas import ApprovalRequest, SecurityAlertOut
from app.security.playbook import SecurityPlaybook
from app.tools.executor import ToolExecutor

router = APIRouter()


@router.get("/security/alerts", response_model=list[SecurityAlertOut])
def list_security_alerts(db: Session = Depends(get_db)) -> list[SecurityAlertOut]:
    """Bảng 3.2: GET /api/security/alerts - danh sách cảnh báo an ninh kèm ánh xạ ATT&CK."""
    alerts = db.execute(select(SecurityAlert).order_by(SecurityAlert.timestamp.desc())).scalars().all()
    return [
        SecurityAlertOut(
            id=a.id,
            timestamp=a.timestamp,
            source_ip=a.source_ip,
            attack_type=a.attack_type,
            severity=a.severity.value,
            status=a.status,
            attack_techniques=[m.technique_id for m in a.attack_mappings],
        )
        for a in alerts
    ]


@router.post("/security/alerts/{alert_id}/approve")
def approve_security_response(
    alert_id: str,
    approval: ApprovalRequest,
    db: Session = Depends(get_db),
    executor: ToolExecutor = Depends(get_tool_executor),
    approver: TokenPayload = Depends(require_approver),
) -> dict:
    """Phê duyệt phản ứng an ninh rủi ro cao (block_ip / isolate_node), đồng nhất guardrail với mục 3.3.2."""
    alert = db.get(SecurityAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo")
    if not approval.approved:
        alert.status = "rejected"
        alert.details = {**(alert.details or {}), "rejected_by": approver.username}
        db.commit()
        return {"status": alert.status}

    playbook = SecurityPlaybook(db=db, executor=executor)
    result = playbook.approve_and_execute(alert)
    return {"status": result.status, "alert_id": result.alert_id}
