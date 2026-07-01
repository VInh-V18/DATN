"""Tương quan sự kiện - mục 2.6, 3.3.1.

Gom nhiều cảnh báo/bất thường rời rạc phát sinh gần nhau về thời gian và có
liên quan trong topology thành một sự cố gốc (incident) duy nhất, tránh agent
xử lý trùng lặp từng cảnh báo riêng lẻ.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.events import emit
from app.models.models import Anomaly, Incident, IncidentStatus, TopologyLink

CORRELATION_WINDOW = timedelta(seconds=30)


def _linked_devices(db: Session, device_id: str) -> set[str]:
    """Trả về tập thiết bị nối trực tiếp với device_id qua topology_links."""
    linked: set[str] = set()
    links = db.execute(select(TopologyLink)).scalars().all()
    for link in links:
        if link.port_a and link.port_a.device_id == device_id and link.port_b:
            linked.add(link.port_b.device_id)
        if link.port_b and link.port_b.device_id == device_id and link.port_a:
            linked.add(link.port_a.device_id)
    return linked


class EventCorrelator:
    def __init__(self, db: Session) -> None:
        self.db = db

    def correlate(self, new_anomaly: Anomaly) -> Incident:
        """Tìm incident mở gần đây cùng cụm thiết bị liên quan để gộp vào, hoặc tạo incident mới."""
        window_start = new_anomaly.timestamp - CORRELATION_WINDOW
        related_devices = _linked_devices(self.db, new_anomaly.device_id) | {new_anomaly.device_id}

        open_incidents = (
            self.db.execute(
                select(Incident).where(
                    Incident.status.in_(
                        [IncidentStatus.open, IncidentStatus.diagnosing, IncidentStatus.awaiting_approval]
                    ),
                    Incident.timestamp >= window_start,
                )
            )
            .scalars()
            .all()
        )

        for incident in open_incidents:
            if related_devices.intersection(incident.device_ids):
                merged = set(incident.device_ids) | {new_anomaly.device_id}
                incident.device_ids = list(merged)
                self.db.commit()
                emit("incident_updated", {"incident_id": incident.id, "status": incident.status.value})
                return incident

        incident = Incident(
            timestamp=new_anomaly.timestamp,
            description=f"Bất thường phát hiện trên thiết bị {new_anomaly.device_id} (điểm={new_anomaly.score:.3f})",
            status=IncidentStatus.open,
            device_ids=[new_anomaly.device_id],
        )
        self.db.add(incident)
        self.db.commit()
        self.db.refresh(incident)
        emit("incident_created", {"incident_id": incident.id, "status": incident.status.value})
        return incident


def now() -> datetime:
    return datetime.utcnow()
