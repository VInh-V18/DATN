"""Syslog UDP listener - nguồn dữ liệu đầu vào thật cho lớp An ninh (mục 3.3.1, 3.3.4).

Đề cương mô tả "lắng nghe syslog theo cơ chế đẩy" (mục 3.3.1) và "dữ liệu đầu
vào gồm syslog, thông tin luồng" (mục 3.3.4). Thiết bị trong GNS3 (Cisco IOS)
có thể được cấu hình `logging host <IP_agent_server> transport udp port <PORT>`
để đẩy bản tin syslog tới đây theo thời gian thực.

Hiện thực rút gọn: mỗi bản tin syslog được ghi vào bảng `events`; các mẫu đăng
nhập SSH thất bại được đưa vào SecurityDetectionEngine.ingest_failed_login() -
khi vượt ngưỡng (Bảng 5.2 KB10), SecurityPlaybook được kích hoạt để ánh xạ
ATT&CK và (nếu đã cấu hình SECURITY_EDGE_DEVICE_ID) đề xuất/chặn IP nguồn.
"""

from __future__ import annotations

import asyncio
import logging
import re

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.events import emit
from app.gns3.client import GNS3Client
from app.models.models import Event, Severity
from app.security.detection import SecurityDetectionEngine
from app.security.playbook import SecurityPlaybook
from app.tools.executor import ToolExecutor

logger = logging.getLogger(__name__)

# Mẫu bản tin thất bại đăng nhập SSH phổ biến trên Cisco IOS / Linux sshd.
FAILED_SSH_PATTERN = re.compile(r"[Ff]ailed (password|login) .*?(?:from|for) (?P<ip>\d{1,3}(?:\.\d{1,3}){3})")

_detection_engine = SecurityDetectionEngine()


def _process_syslog_line(source_ip: str, message: str) -> None:
    db = SessionLocal()
    try:
        db.add(Event(source=source_ip, severity=Severity.info, content=message))
        db.commit()

        match = FAILED_SSH_PATTERN.search(message)
        if not match:
            return

        result = _detection_engine.ingest_failed_login(match.group("ip"))
        if result is None:
            return

        settings = get_settings()
        edge_device_id = settings.security_edge_device_id
        try:
            with GNS3Client() as gns3:
                executor = ToolExecutor(db=db, gns3_client=gns3, project_id=settings.gns3_project_id or "")
                playbook = SecurityPlaybook(db=db, executor=executor)
                playbook_result = playbook.handle_detection(result, edge_node_id=edge_device_id)
            emit(
                "security_alert_updated",
                {"alert_id": playbook_result.alert_id, "status": playbook_result.status},
            )
        except Exception:
            logger.exception("Không thể chạy playbook phản ứng cho cảnh báo từ %s", source_ip)
    finally:
        db.close()


class _SyslogProtocol(asyncio.DatagramProtocol):
    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        message = data.decode("utf-8", errors="ignore").strip()
        if not message:
            return
        asyncio.ensure_future(asyncio.to_thread(_process_syslog_line, addr[0], message))


async def run_syslog_listener(stop_event: asyncio.Event | None = None) -> None:
    """Chạy UDP server lắng nghe syslog cho tới khi stop_event được set."""
    settings = get_settings()
    stop_event = stop_event or asyncio.Event()
    loop = asyncio.get_running_loop()

    try:
        transport, _ = await loop.create_datagram_endpoint(
            _SyslogProtocol, local_addr=(settings.syslog_udp_host, settings.syslog_udp_port)
        )
    except OSError:
        logger.exception(
            "Không thể mở cổng UDP %s:%s cho syslog listener - có thể cần quyền root cho cổng < 1024",
            settings.syslog_udp_host,
            settings.syslog_udp_port,
        )
        return

    try:
        await stop_event.wait()
    finally:
        transport.close()
