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

from sqlalchemy.orm import Session

from app.automation.device_client import DeviceClient, DeviceCredentials
from app.core.config import get_settings
from app.models.models import Anomaly, Device
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


def collect_device_sample(device: Device) -> list[float] | None:
    if not device.management_address:
        return None
    try:
        with DeviceClient(DeviceCredentials.for_device(device.management_address)) as dc:
            cpu_raw = dc.send_command("show processes cpu")
            interfaces = dc.get_interfaces_status()
            down_count = sum(1 for i in interfaces if i["status"].lower() != "up")
            cpu = _parse_cpu_percent(cpu_raw)
            return build_feature_vector(
                cpu_percent=cpu,
                memory_percent=0.0,
                bandwidth_in_mbps=0.0,
                bandwidth_out_mbps=0.0,
                packet_loss_rate=0.0,
                interface_errors=0.0,
                port_flap_count=float(down_count),
                syslog_rate=0.0,
            )
    except Exception:  # thiết bị có thể đang tắt hoặc không truy cập được
        logger.exception("Không thể thu thập số liệu từ thiết bị %s", device.id)
        return None


def collect_once(db: Session, devices: list[Device]) -> list[Anomaly]:
    metrics_store = InfluxMetricsStore()
    correlator = EventCorrelator(db)
    new_anomalies: list[Anomaly] = []

    for device in devices:
        vector = collect_device_sample(device)
        if vector is None:
            continue

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
