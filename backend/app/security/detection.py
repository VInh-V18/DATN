"""Module phát hiện tấn công - luật ngưỡng kết hợp học máy (mục 2.7, 3.3.4).

Ba luật tiêu biểu theo đề cương:
- Quét cổng: số cổng đích bị truy cập từ cùng một IP vượt ngưỡng trong cửa sổ ngắn.
- SYN flood: số kết nối nửa mở (half-open) tăng đột biến.
- Dò mật khẩu SSH: số lần đăng nhập thất bại liên tiếp vượt ngưỡng.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta

PORT_SCAN_WINDOW = timedelta(seconds=10)
PORT_SCAN_DISTINCT_PORT_THRESHOLD = 15

SYN_FLOOD_WINDOW = timedelta(seconds=5)
SYN_FLOOD_COUNT_THRESHOLD = 100

SSH_BRUTEFORCE_WINDOW = timedelta(seconds=60)
SSH_BRUTEFORCE_FAILURE_THRESHOLD = 5


@dataclass
class DetectionResult:
    indicator: str
    source_ip: str
    detail: dict


class SecurityDetectionEngine:
    """Bộ phát hiện dựa trên cửa sổ trượt trong bộ nhớ.

    Trong triển khai thật, các sự kiện flow/syslog được đẩy vào từ collector
    (netflow, syslog server); ở đây expose các hàm ingest_* để nạp sự kiện và
    check_* để soi luật, phù hợp dùng trong test và trong vòng lặp giám sát.
    """

    def __init__(self) -> None:
        self._port_hits: dict[str, deque[tuple[datetime, int]]] = defaultdict(deque)
        self._syn_hits: dict[str, deque[datetime]] = defaultdict(deque)
        self._login_failures: dict[str, deque[datetime]] = defaultdict(deque)

    def ingest_flow(self, src_ip: str, dst_port: int, timestamp: datetime | None = None) -> DetectionResult | None:
        ts = timestamp or datetime.utcnow()
        window = self._port_hits[src_ip]
        window.append((ts, dst_port))
        self._evict(window, ts, PORT_SCAN_WINDOW)
        distinct_ports = {port for _, port in window}
        if len(distinct_ports) >= PORT_SCAN_DISTINCT_PORT_THRESHOLD:
            return DetectionResult(
                indicator="port_scan", source_ip=src_ip, detail={"distinct_ports": len(distinct_ports)}
            )
        return None

    def ingest_syn(self, src_ip: str, timestamp: datetime | None = None) -> DetectionResult | None:
        ts = timestamp or datetime.utcnow()
        window = self._syn_hits[src_ip]
        window.append(ts)
        self._evict(window, ts, SYN_FLOOD_WINDOW)
        if len(window) >= SYN_FLOOD_COUNT_THRESHOLD:
            return DetectionResult(indicator="syn_flood", source_ip=src_ip, detail={"half_open_count": len(window)})
        return None

    def ingest_failed_login(self, src_ip: str, timestamp: datetime | None = None) -> DetectionResult | None:
        ts = timestamp or datetime.utcnow()
        window = self._login_failures[src_ip]
        window.append(ts)
        self._evict(window, ts, SSH_BRUTEFORCE_WINDOW)
        if len(window) >= SSH_BRUTEFORCE_FAILURE_THRESHOLD:
            return DetectionResult(
                indicator="ssh_bruteforce", source_ip=src_ip, detail={"failed_attempts": len(window)}
            )
        return None

    @staticmethod
    def _evict(window: deque, now: datetime, max_age: timedelta) -> None:
        while window:
            item = window[0]
            item_ts = item[0] if isinstance(item, tuple) else item
            if now - item_ts > max_age:
                window.popleft()
            else:
                break
