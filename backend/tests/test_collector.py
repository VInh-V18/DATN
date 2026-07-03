import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.monitoring.collector as collector_module
from app.core.database import Base
from app.models.models import Device, DeviceRole, Incident, IncidentStatus, Interface, LinkStatus, TopologyLink
from app.monitoring.anomaly import AnomalyScore
from app.monitoring.collector import _parse_port_number, sync_interface_status


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_parse_port_number() -> None:
    assert _parse_port_number("GigabitEthernet0/1") == 1
    assert _parse_port_number("FastEthernet0/0") == 0
    assert _parse_port_number("Loopback0") is None


def test_sync_interface_status_updates_link(db_session) -> None:
    r2 = Device(name="R2", node_type="Cisco IOSv", role=DeviceRole.router)
    r3 = Device(name="R3", node_type="Cisco IOSv", role=DeviceRole.router)
    db_session.add_all([r2, r3])
    db_session.flush()

    iface_r2 = Interface(device_id=r2.id, name="port1", status=LinkStatus.down)
    iface_r3 = Interface(device_id=r3.id, name="port0", status=LinkStatus.down)
    db_session.add_all([iface_r2, iface_r3])
    db_session.flush()

    link = TopologyLink(port_a_id=iface_r2.id, port_b_id=iface_r3.id, status=LinkStatus.down)
    db_session.add(link)
    db_session.commit()

    # R2 báo cổng up nhưng R3 vẫn down -> link vẫn phải là down.
    changed = sync_interface_status(db_session, r2, [{"name": "GigabitEthernet0/1", "status": "up", "ip_address": "10.0.0.1"}])
    assert changed is True
    db_session.refresh(link)
    assert iface_r2.status == LinkStatus.up
    assert link.status == LinkStatus.down

    # R3 cũng lên -> link phải chuyển thành up.
    changed = sync_interface_status(db_session, r3, [{"name": "GigabitEthernet0/0", "status": "up", "ip_address": "10.0.0.2"}])
    assert changed is True
    db_session.refresh(link)
    assert link.status == LinkStatus.up

    # Gọi lại với cùng trạng thái - không có thay đổi nào.
    changed = sync_interface_status(db_session, r3, [{"name": "GigabitEthernet0/0", "status": "up", "ip_address": "10.0.0.2"}])
    assert changed is False


def test_sync_interface_status_ignores_unmapped_interface(db_session) -> None:
    device = Device(name="H1", node_type="VPCS", role=DeviceRole.host)
    db_session.add(device)
    db_session.commit()

    changed = sync_interface_status(db_session, device, [{"name": "Loopback0", "status": "up", "ip_address": None}])
    assert changed is False


class _AlwaysAnomalyDetector:
    """Giả lập AnomalyDetector luôn báo bất thường - dùng để test dispatch mà
    không cần huấn luyện Isolation Forest thật."""

    def fit(self, history: list) -> None:
        pass

    def score_single(self, vector: list[float]) -> AnomalyScore:
        return AnomalyScore(is_anomaly=True, score=-0.9, features={})


class _NoopMetricsStore:
    def write_metric(self, *args, **kwargs) -> None:
        pass

    def close(self) -> None:
        pass


def test_collect_once_dispatches_newly_created_open_incident(db_session, monkeypatch) -> None:
    device = Device(name="R1", node_type="Cisco IOSv", role=DeviceRole.router, management_address="10.0.0.1")
    db_session.add(device)
    db_session.commit()

    monkeypatch.setattr(collector_module, "collect_device_sample", lambda d: ([0.0] * 8, []))
    monkeypatch.setattr(collector_module, "_detectors", {})
    monkeypatch.setattr(collector_module, "_history", {})
    monkeypatch.setattr(collector_module, "AnomalyDetector", _AlwaysAnomalyDetector)
    monkeypatch.setattr(collector_module, "InfluxMetricsStore", _NoopMetricsStore)

    new_anomalies, incidents_to_dispatch = collector_module.collect_once(db_session, [device])

    assert len(new_anomalies) == 1
    assert len(incidents_to_dispatch) == 1
    incident = db_session.get(Incident, incidents_to_dispatch[0])
    assert incident.status == IncidentStatus.open
    assert device.id in incident.device_ids


def test_collect_once_does_not_dispatch_incident_already_being_handled(db_session, monkeypatch) -> None:
    """Nếu sự cố được gộp vào một incident đã đang được agent xử lý (không còn
    "open"), Orchestrator không nên giao việc lại (tránh chạy trùng agent)."""
    device = Device(name="R1", node_type="Cisco IOSv", role=DeviceRole.router, management_address="10.0.0.1")
    db_session.add(device)
    db_session.commit()

    existing = Incident(description="Đang xử lý", status=IncidentStatus.remediating, device_ids=[device.id])
    db_session.add(existing)
    db_session.commit()

    monkeypatch.setattr(collector_module, "collect_device_sample", lambda d: ([0.0] * 8, []))
    monkeypatch.setattr(collector_module, "_detectors", {})
    monkeypatch.setattr(collector_module, "_history", {})
    monkeypatch.setattr(collector_module, "AnomalyDetector", _AlwaysAnomalyDetector)
    monkeypatch.setattr(collector_module, "InfluxMetricsStore", _NoopMetricsStore)

    # Ép tương quan gộp bất thường mới vào incident đang xử lý ở trên.
    monkeypatch.setattr(
        collector_module.EventCorrelator, "correlate", lambda self, anomaly: existing
    )

    _, incidents_to_dispatch = collector_module.collect_once(db_session, [device])

    assert incidents_to_dispatch == []


@pytest.mark.asyncio
async def test_run_collector_loop_dispatches_incidents_via_orchestrator(monkeypatch) -> None:
    dispatched: list[str] = []

    async def fake_dispatch(incident_id: str) -> None:
        dispatched.append(incident_id)

    monkeypatch.setattr(collector_module.orchestrator, "dispatch_incident", fake_dispatch)
    monkeypatch.setattr(collector_module, "collect_once", lambda db, devices: ([], ["inc-1", "inc-2"]))

    class _FakeQuery:
        def all(self):
            return []

    class _FakeSession:
        def query(self, model):
            return _FakeQuery()

        def close(self):
            pass

    stop_event = asyncio.Event()

    async def stop_after_first_iteration():
        await asyncio.sleep(0.05)
        stop_event.set()

    await asyncio.gather(
        collector_module.run_collector_loop(lambda: _FakeSession(), stop_event),
        stop_after_first_iteration(),
    )

    assert dispatched == ["inc-1", "inc-2"]
