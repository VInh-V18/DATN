"""Dựng lab GNS3 và đồng bộ dữ liệu vào DB - mục 5.1, Bảng 5.1, GĐ1 (Bảng 5.4).

Sử dụng:
    python -m scripts.gns3_lab create              # tạo project + node + link trên GNS3
    python -m scripts.gns3_lab seed-db             # ghi devices/interfaces/topology_links vào DB
    python -m scripts.gns3_lab create --seed-db    # làm cả hai, theo đúng thứ tự

Cấu hình topology đọc từ `backend/lab_topology.yaml` (chỉnh sửa `template_name`
cho khớp với các template đã đăng ký trên GNS3 server của bạn trước khi chạy).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.gns3.client import GNS3Client
from app.models.models import Device, DeviceRole, Interface, LinkStatus, TopologyLink

TOPOLOGY_PATH = Path(__file__).resolve().parents[1] / "lab_topology.yaml"


def load_topology() -> dict:
    with open(TOPOLOGY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_gns3_lab(topology: dict) -> str:
    """Tạo project và node trên GNS3 theo cấu hình; trả về project_id.

    Yêu cầu GNS3 server đang chạy (mục 2.4) và các template trong
    `lab_topology.yaml` đã được đăng ký sẵn.
    """
    with GNS3Client() as gns3:
        project = gns3.find_project_by_name(topology["project_name"])
        if project is None:
            print(f"Tạo project GNS3 mới: {topology['project_name']}")
            project = gns3.create_project(topology["project_name"])
        else:
            print(f"Dùng lại project GNS3 đã có: {project['name']} ({project['project_id']})")
        project_id = project["project_id"]

        template_cache: dict[str, dict] = {}
        for device in topology["devices"]:
            existing = gns3.find_node_by_name(project_id, device["name"])
            if existing is not None:
                print(f"  - Node '{device['name']}' đã tồn tại, bỏ qua.")
                continue

            template_name = device["template_name"]
            template = template_cache.get(template_name) or gns3.find_template_by_name(template_name)
            if template is None:
                print(
                    f"  ! Không tìm thấy template '{template_name}' cho thiết bị '{device['name']}' "
                    "trên GNS3 server - hãy đăng ký template này trước hoặc sửa lab_topology.yaml."
                )
                continue
            template_cache[template_name] = template

            node = gns3.create_node_from_template(
                project_id,
                template["template_id"],
                name=device["name"],
                x=device.get("x", 0),
                y=device.get("y", 0),
            )
            print(f"  - Đã tạo node '{device['name']}' (node_id={node['node_id']})")

        nodes_by_name = {n["name"]: n for n in gns3.list_nodes(project_id)}
        for link in topology.get("links", []):
            node_a, node_b = nodes_by_name.get(link["a"]), nodes_by_name.get(link["b"])
            if node_a is None or node_b is None:
                print(f"  ! Bỏ qua liên kết {link['a']}-{link['b']}: thiếu node.")
                continue
            try:
                gns3.create_link(project_id, node_a["node_id"], link["a_port"], node_b["node_id"], link["b_port"])
                print(f"  - Đã tạo liên kết {link['a']}(port {link['a_port']}) - {link['b']}(port {link['b_port']})")
            except Exception as exc:  # liên kết có thể đã tồn tại hoặc cổng không hợp lệ
                print(f"  ! Không thể tạo liên kết {link['a']}-{link['b']}: {exc}")

        return project_id


def seed_db(topology: dict, project_id: str | None = None) -> None:
    """Ghi devices/interfaces/topology_links vào DB quan hệ (mục 3.5) từ cấu hình lab.

    Nếu `project_id` được cung cấp (hoặc tìm thấy trên GNS3), sẽ gắn kèm gns3_node_id
    tương ứng để agent có thể điều khiển qua GNS3 REST API.
    """
    Base.metadata.create_all(bind=engine)

    nodes_by_name: dict[str, dict] = {}
    if project_id is None:
        try:
            with GNS3Client() as gns3:
                project = gns3.find_project_by_name(topology["project_name"])
                if project is not None:
                    project_id = project["project_id"]
                    nodes_by_name = {n["name"]: n for n in gns3.list_nodes(project_id)}
        except Exception as exc:
            print(f"  ! Không kết nối được GNS3 để lấy gns3_node_id ({exc}); vẫn tiếp tục seed DB.")

    db = SessionLocal()
    try:
        device_by_name: dict[str, Device] = {}
        for spec in topology["devices"]:
            device = db.query(Device).filter_by(name=spec["name"]).first()
            if device is None:
                device = Device(name=spec["name"], node_type=spec["template_name"], role=DeviceRole(spec["role"]))
                db.add(device)
            device.node_type = spec["template_name"]
            device.role = DeviceRole(spec["role"])
            gns3_node = nodes_by_name.get(spec["name"])
            if gns3_node is not None:
                device.gns3_node_id = gns3_node["node_id"]
            db.flush()
            device_by_name[spec["name"]] = device
        db.commit()

        interface_cache: dict[tuple[str, int], Interface] = {}

        def _get_or_create_interface(device_name: str, port: int) -> Interface:
            key = (device_name, port)
            if key in interface_cache:
                return interface_cache[key]
            device = device_by_name[device_name]
            iface_name = f"port{port}"
            iface = db.query(Interface).filter_by(device_id=device.id, name=iface_name).first()
            if iface is None:
                iface = Interface(device_id=device.id, name=iface_name, status=LinkStatus.down)
                db.add(iface)
                db.flush()
            interface_cache[key] = iface
            return iface

        for link in topology.get("links", []):
            if link["a"] not in device_by_name or link["b"] not in device_by_name:
                continue
            iface_a = _get_or_create_interface(link["a"], link["a_port"])
            iface_b = _get_or_create_interface(link["b"], link["b_port"])
            existing = (
                db.query(TopologyLink)
                .filter_by(port_a_id=iface_a.id, port_b_id=iface_b.id)
                .first()
            )
            if existing is None:
                db.add(TopologyLink(port_a_id=iface_a.id, port_b_id=iface_b.id, status=LinkStatus.down))

        db.commit()
        print(f"Đã seed {len(device_by_name)} thiết bị và {len(topology.get('links', []))} liên kết vào DB.")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "seed-db"], help="Hành động cần thực hiện")
    parser.add_argument("--seed-db", action="store_true", help="Khi dùng với 'create': seed DB luôn sau khi tạo lab")
    args = parser.parse_args()

    topology = load_topology()
    settings = get_settings()

    if args.action == "create":
        project_id = create_gns3_lab(topology)
        print(f"Xong. GNS3_PROJECT_ID={project_id} (nhớ cập nhật vào backend/.env)")
        if args.seed_db:
            seed_db(topology, project_id=project_id)
    elif args.action == "seed-db":
        seed_db(topology, project_id=settings.gns3_project_id)


if __name__ == "__main__":
    sys.exit(main())
