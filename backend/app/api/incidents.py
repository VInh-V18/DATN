from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.self_healing import SelfHealingAgent
from app.api.deps import get_llm, get_tool_executor, require_approver
from app.core.database import get_db
from app.core.security import TokenPayload
from app.llm.client import LLMClient
from app.models.models import ActionLog, Incident
from app.schemas.schemas import ActionLogOut, ApprovalRequest, IncidentOut
from app.tools.executor import ToolExecutor

router = APIRouter()


@router.get("/incidents", response_model=list[IncidentOut])
def list_incidents(db: Session = Depends(get_db)) -> list[Incident]:
    """Bảng 3.2: GET /api/incidents - danh sách sự cố và trạng thái xử lý."""
    return list(db.execute(select(Incident).order_by(Incident.timestamp.desc())).scalars().all())


@router.get("/incidents/{incident_id}/actions", response_model=list[ActionLogOut])
def get_incident_actions(incident_id: str, db: Session = Depends(get_db)) -> list[ActionLog]:
    """Bảng 3.2: GET /api/incidents/{id}/actions - nhật ký hành động của agent cho một sự cố."""
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy sự cố")
    return list(
        db.execute(select(ActionLog).where(ActionLog.incident_id == incident_id).order_by(ActionLog.timestamp))
        .scalars()
        .all()
    )


@router.post("/incidents/{incident_id}/approve", response_model=IncidentOut)
def approve_incident_action(
    incident_id: str,
    approval: ApprovalRequest,
    db: Session = Depends(get_db),
    executor: ToolExecutor = Depends(get_tool_executor),
    llm: LLMClient = Depends(get_llm),
    approver: TokenPayload = Depends(require_approver),
) -> Incident:
    """Bảng 3.2: POST /api/incidents/{id}/approve - phê duyệt hành động khắc phục (UC4, chỉ kỹ sư/admin)."""
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy sự cố")
    if incident.pending_action is None:
        raise HTTPException(status_code=400, detail="Sự cố không có hành động nào đang chờ phê duyệt")

    if not approval.approved:
        incident.pending_action = {**incident.pending_action, "approved": False, "approver": approver.username}
        db.commit()
        db.refresh(incident)
        return incident

    incident.pending_action = {**incident.pending_action, "approved": True, "approver": approver.username}
    db.commit()

    agent = SelfHealingAgent(db=db, executor=executor, llm=llm)
    agent.tu_khac_phuc(incident_id)
    db.refresh(incident)
    return incident
