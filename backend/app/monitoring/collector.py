"""Thành phần thu thập (collector) - mục 3.3.1.

Định kỳ truy vấn GNS3 REST API và thiết bị để lấy trạng thái, đưa số liệu vào
InfluxDB, chạy Isolation Forest để phát hiện bất thường và chuyển kết quả sang
module tương quan sự kiện.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.automation.device_client import DeviceClient, DeviceCredentials
from app.core.config import get_settings
from app.core.events import emit
from app.models.models import ActionLog, Anomaly, Device, Incident, IncidentStatus, Interface, LinkStatus, TopologyLink
from app.monitoring.anomaly import AnomalyDetector, build_feature_vector
from app.monitoring.correlation import EventCorrelator
from app.monitoring.influx_client import InfluxMetricsStore
from app.orchestrator import orchestrator

logger = logging.getLogger(__name__)

# Nếu SelfHealingAgent gặp lỗi giữa chừng (LLM/SSH timeout, ngoại lệ chưa
# lường trước...), sự cố có thể kẹt mãi ở "diagnosing"/"remediating" vì trạng
# thái này đã được ghi (commit) trước khi lỗi xảy ra và không có gì tự retry.
# STUCK_RECOVERY_THRESHOLD định nghĩa sau bao lâu kể từ lần chạm cuối (hành
# động gần nhất, hoặc lúc tạo nếu chưa có hành động nào) thì coi là "kẹt" và
# giao lại cho Orchestrator xử lý tiếp.
STUCK_RECOVERY_THRESHOLD = timedelta(minutes=2)
_STUCK_STATUSES = (IncidentStatus.diagnosing, IncidentStatus.remediating)

# Bộ nhớ đệm mô hình theo từng thiết bị và lịch sử vec-tơ đặc trưng gần nhất,
# dùng để huấn luyện Isolation Forest theo kiểu cửa sổ trượt (sliding window).
_detectors: dict[str, AnomalyDetector] = {}
_history: dict[str, list[list[float]]] = {}
HISTORY_WINDOW = 200


def _parse_cpu_percent(show_processes_cpu: str) -> float:
    match = re.search(r"CPU utilization for five seconds:\s*(\d+)%", show_processes_cpu)
    return float(match.group(1)) if match else 0.0


# `scripts/gns3_lab.py` seed các interface với tên quy ước "portN" (N là số cổng
# adapter trong lab_topology.yaml), trong khi thiết bị thật trả về tên kiểu
# "GigabitEthernet0/1". Với các template một khe cắm (ví dụ Cisco IOSv trong
# GNS3), số sau dấu "/" cuối cùng chính là số cổng adapter - dùng làm cầu nối
# giữa tên interface thật và tên đã seed. Đây là suy đoán phù hợp quy mô lab,
# không đúng với mọi loại thiết bị/slot phức tạp.
_PORT_NUMBER_PATTERN = re.compile(r"/(\d+)$")


def _parse_port_number(interface_name: str) -> int | None:
    match = _PORT_NUMBER_PATTERN.search(interface_name)
    return int(match.group(1)) if match else None


def collect_device_sample(device: Device) -> tuple[list[float], list[dict]] | None:
    if not device.management_address:
        return None
    try:
        with DeviceClient(DeviceCredentials.for_device(device.management_address)) as dc:
            cpu_raw = dc.send_command("show processes cpu")
            interfaces = dc.get_interfaces_status()
            down_count = sum(1 for i in interfaces if i["status"].lower() != "up")
            cpu = _parse_cpu_percent(cpu_raw)
            vector = build_feature_vector(
                cpu_percent=cpu,
                memory_percent=0.0,
                bandwidth_in_mbps=0.0,
                bandwidth_out_mbps=0.0,
                packet_loss_rate=0.0,
                interface_errors=0.0,
                port_flap_count=float(down_count),
                syslog_rate=0.0,
            )
            return vector, interfaces
    except Exception:  # thiết bị có thể đang tắt hoặc không truy cập được
        logger.exception("Không thể thu thập số liệu từ thiết bị %s", device.id)
        return None


def sync_interface_status(db: Session, device: Device, live_interfaces: list[dict]) -> bool:
    """Ghi trạng thái interface thật (đọc qua Netmiko) vào bảng interfaces/topology_links.

    Trả về True nếu có ít nhất một interface/link đổi trạng thái - dùng để quyết
    định có cần phát sự kiện `topology_updated` hay không (UC1: giám sát trạng
    thái mạng theo thời gian thực, Bảng 3.2 GET /api/topology).
    """
    changed = False
    touched_interface_ids: set[str] = set()

    for live in live_interfaces:
        port_number = _parse_port_number(live["name"])
        if port_number is None:
            continue
        seeded_name = f"port{port_number}"
        iface = db.query(Interface).filter_by(device_id=device.id, name=seeded_name).first()
        if iface is None:
            continue  # interface chưa được seed vào DB (xem scripts/gns3_lab.py)

        new_status = LinkStatus.up if live["status"].lower() == "up" else LinkStatus.down
        if iface.status != new_status or iface.ip_address != live.get("ip_address"):
            iface.status = new_status
            iface.ip_address = live.get("ip_address")
            changed = True
        touched_interface_ids.add(iface.id)

    if touched_interface_ids:
        links = db.execute(
            select(TopologyLink).where(
                TopologyLink.port_a_id.in_(touched_interface_ids) | TopologyLink.port_b_id.in_(touched_interface_ids)
            )
        ).scalars().all()
        for link in links:
            both_up = link.port_a.status == LinkStatus.up and link.port_b.status == LinkStatus.up
            new_link_status = LinkStatus.up if both_up else LinkStatus.down
            if link.status != new_link_status:
                link.status = new_link_status
                changed = True

    if changed:
        db.commit()
    return changed


def find_stuck_incidents(db: Session, now: datetime | None = None) -> list[str]:
    """Tìm các sự cố đang ở trạng thái diagnosing/remediating nhưng đã lâu
    không có hành động nào mới - dấu hiệu SelfHealingAgent đã crash giữa
    chừng (ví dụ lỗi gọi LLM hoặc mất kết nối SSH) và cần được giao lại.
    """
    now = now or datetime.utcnow()
    candidates = db.execute(select(Incident).where(Incident.status.in_(_STUCK_STATUSES))).scalars().all()

    stuck_ids: list[str] = []
    for incident in candidates:
        last_action = (
            db.execute(
                select(ActionLog).where(ActionLog.incident_id == incident.id).order_by(ActionLog.timestamp.desc())
            )
            .scalars()
            .first()
        )
        last_touched = last_action.timestamp if last_action else incident.timestamp
        if now - last_touched > STUCK_RECOVERY_THRESHOLD:
            stuck_ids.append(incident.id)
    return stuck_ids


def collect_once(db: Session, devices: list[Device]) -> tuple[list[Anomaly], list[str]]:
    """Trả về (các bất thường mới, các incident_id cần giao cho SelfHealingAgent).

    Một incident cần giao việc khi vẫn đang ở trạng thái "open" - nghĩa là
    MonitorAgent (collector + tương quan sự kiện) vừa tạo/cập nhật nó và chưa
    agent nào bắt đầu xử lý (xem app.orchestrator.Orchestrator).
    """
    metrics_store = InfluxMetricsStore()
    correlator = EventCorrelator(db)
    new_anomalies: list[Anomaly] = []
    incidents_to_dispatch: list[str] = []

    topology_changed = False
    for device in devices:
        sample = collect_device_sample(device)
        if sample is None:
            continue
        vector, live_interfaces = sample

        if sync_interface_status(db, device, live_interfaces):
            topology_changed = True

        metrics_store.write_metric(
            device.id,
            fields=dict(
                zip(
                    [
                        "cpu_percent",
                        "memory_percent",
                        "bandwidth_in_mbps",
                        "bandwidth_out_mbps",
                        "packet_loss_rate",
                        "interface_errors",
                        "port_flap_count",
                        "syslog_rate",
                    ],
                    vector,
                )
            ),
        )

        history = _history.setdefault(device.id, [])
        history.append(vector)
        if len(history) > HISTORY_WINDOW:
            history.pop(0)

        detector = _detectors.setdefault(device.id, AnomalyDetector())
        detector.fit(history)
        result = detector.score_single(vector)

        if result.is_anomaly:
            anomaly = Anomaly(
                timestamp=datetime.utcnow(),
                device_id=device.id,
                score=result.score,
                features=result.features,
            )
            db.add(anomaly)
            db.commit()
            db.refresh(anomaly)
            incident = correlator.correlate(anomaly)
            if incident.status == IncidentStatus.open and incident.id not in incidents_to_dispatch:
                incidents_to_dispatch.append(incident.id)
            new_anomalies.append(anomaly)

    metrics_store.close()
    if topology_changed:
        emit("topology_updated", {})

    for incident_id in find_stuck_incidents(db):
        if incident_id not in incidents_to_dispatch:
            logger.warning("Sự cố %s kẹt quá lâu ở trạng thái xử lý - giao lại cho SelfHealingAgent", incident_id)
            incidents_to_dispatch.append(incident_id)

    return new_anomalies, incidents_to_dispatch


async def run_collector_loop(session_factory, stop_event: asyncio.Event | None = None) -> None:
    """Vòng lặp nền chạy định kỳ (mặc định 5-15 giây, mục 3.3.1).

    Sau mỗi chu kỳ thu thập, các sự cố mới phát hiện được giao ngay cho
    SelfHealingAgent qua Orchestrator (chạy trong thread pool riêng - xem
    app.orchestrator - để không chặn vòng lặp sự kiện async của FastAPI).
    """
    settings = get_settings()
    stop_event = stop_event or asyncio.Event()
    while not stop_event.is_set():
        db = session_factory()
        incidents_to_dispatch: list[str] = []
        try:
            devices = db.query(Device).all()
            _, incidents_to_dispatch = collect_once(db, devices)
        except Exception:
            logger.exception("Lỗi trong vòng lặp thu thập dữ liệu giám sát")
        finally:
            db.close()

        for incident_id in incidents_to_dispatch:
            await orchestrator.dispatch_incident(incident_id)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.collector_interval_seconds)
        except asyncio.TimeoutError:
            pass
