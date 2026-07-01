import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.models import Device, DeviceRole, Interface, LinkStatus, TopologyLink
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
