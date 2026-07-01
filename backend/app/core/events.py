"""Cầu nối sự kiện đồng bộ -> WebSocket bất đồng bộ.

Các module nghiệp vụ (agent self-healing, monitoring, security playbook) chạy
đồng bộ trên SQLAlchemy Session và không nên phụ thuộc trực tiếp vào vòng lặp
asyncio của FastAPI/WebSocket. Chúng chỉ cần gọi `emit()` (thread-safe); một
tác vụ nền trong `app.main` sẽ tiêu thụ hàng đợi này và phát ra kênh
`/ws/events` (Bảng 3.2), phục vụ cập nhật thời gian thực cho dashboard.
"""

from __future__ import annotations

import queue
from typing import Any

event_queue: "queue.Queue[tuple[str, dict[str, Any]]]" = queue.Queue()


def emit(event_type: str, payload: dict[str, Any]) -> None:
    event_queue.put((event_type, payload))
