from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Device
from app.monitoring.influx_client import InfluxMetricsStore
from app.schemas.schemas import DeviceOut

router = APIRouter()


@router.get("/devices", response_model=list[DeviceOut])
def list_devices(db: Session = Depends(get_db)) -> list[Device]:
    return list(db.execute(select(Device)).scalars().all())


@router.get("/devices/{device_id}/status", response_model=DeviceOut)
def get_device_status(device_id: str, db: Session = Depends(get_db)) -> Device:
    """Bảng 3.2: GET /api/devices/{id}/status - trạng thái và cấu hình của một thiết bị."""
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy thiết bị")
    return device


@router.get("/metrics")
def get_metrics(device_id: str, time_range: str = "-15m") -> list[dict]:
    """Bảng 3.2: GET /api/metrics - truy vấn số liệu time-series theo thiết bị và khoảng thời gian."""
    store = InfluxMetricsStore()
    try:
        return store.query_metrics(device_id=device_id, time_range=time_range)
    finally:
        store.close()
