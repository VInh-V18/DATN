from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import AgentTrace, TraceSubjectType
from app.schemas.schemas import AgentTraceOut

router = APIRouter()


@router.get("/agent-traces", response_model=list[AgentTraceOut])
def list_agent_traces(
    subject_type: str | None = None,
    subject_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[AgentTrace]:
    """Nhật ký suy luận (audit trail) của các agent - dùng cho trang hoạt động
    đa tác tử và panel chi tiết sự cố/cảnh báo an ninh.

    Không lọc gì -> trả về hoạt động gần nhất của TẤT CẢ agent (Tự khắc phục +
    An ninh), phù hợp cho một khu vực "hoạt động trực tiếp" tổng quan.
    """
    query = select(AgentTrace).order_by(AgentTrace.timestamp.desc()).limit(min(limit, 500))
    if subject_type:
        query = query.where(AgentTrace.subject_type == TraceSubjectType(subject_type))
    if subject_id:
        query = query.where(AgentTrace.subject_id == subject_id)
    return list(db.execute(query).scalars().all())
