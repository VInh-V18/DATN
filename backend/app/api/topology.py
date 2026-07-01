from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Device, TopologyLink
from app.schemas.schemas import TopologyOut

router = APIRouter()


@router.get("/topology", response_model=TopologyOut)
def get_topology(db: Session = Depends(get_db)) -> TopologyOut:
    """Bảng 3.2: GET /api/topology - lấy sơ đồ mạng cùng trạng thái node và liên kết."""
    devices = db.execute(select(Device)).scalars().all()
    links = db.execute(select(TopologyLink)).scalars().all()
    return TopologyOut(devices=list(devices), links=list(links))
