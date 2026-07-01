"""Thành phần thu thập (collector) - mục 3.3.1.

Định kỳ truy vấn GNS3 REST API và thiết bị để lấy trạng thái, đưa số liệu vào
InfluxDB, chạy Isolation Forest để phát hiện bất thường và chuyển kết quả sang
module tương quan sự kiện.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.automation.device_client import DeviceClient, DeviceCredentials
from app.core.config import get_settings
from app.core.events import emit
from app.models.models import Anomaly, Device, Interface, LinkStatus, TopologyLink
from app.monitoring.anomaly import AnomalyDetector, build_feature_vector
from app.monitoring.correlation import EventCorrelator
from app.monitoring.influx_client import InfluxMetricsStore

logger = logging.getLogger(__name__)

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


def collect_once(db: Session, devices: list[Device]) -> list[Anomaly]:
    metrics_store = InfluxMetricsStore()
    correlator = EventCorrelator(db)
    new_anomalies: list[Anomaly] = []

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
            correlator.correlate(anomaly)
            new_anomalies.append(anomaly)

    metrics_store.close()
    if topology_changed:
        emit("topology_updated", {})
    return new_anomalies


async def run_collector_loop(session_factory, stop_event: asyncio.Event | None = None) -> None:
    """Vòng lặp nền chạy định kỳ (mặc định 5-15 giây, mục 3.3.1)."""
    settings = get_settings()
    stop_event = stop_event or asyncio.Event()
    while not stop_event.is_set():
        db = session_factory()
        try:
            devices = db.query(Device).all()
            collect_once(db, devices)
        except Exception:
            logger.exception("Lỗi trong vòng lặp thu thập dữ liệu giám sát")
        finally:
            db.close()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.collector_interval_seconds)
        except asyncio.TimeoutError:
            pass
