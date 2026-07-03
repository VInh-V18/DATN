"""Kiểu dữ liệu và cổng (ports) dùng chung cho lõi agent.

Module này (và các module khác trong `app.agent_core`) KHÔNG được import bất
cứ thứ gì từ SQLAlchemy, FastAPI hay `app.models`. Đây là ranh giới kiến trúc
cố ý: lõi suy luận (ReAct, tự khắc phục, copilot) phải chạy được độc lập,
kiểm thử được bằng một LLM giả lập và một "thiết bị" giả lập, không cần
PostgreSQL/GNS3 nào cả (xem `app.agent_core.fakes` và `scripts/demo_agent.py`).

Việc kết nối tới hệ thống thật (DB, GNS3, Netmiko) được các lớp adapter trong
`app.agent` / `app.copilot` / `app.tools.runner` đảm nhiệm, thông qua hai cổng
(Protocol) khai báo dưới đây:

- `ToolRunner`  : thực thi một tool theo tên + tham số, trả về `ToolOutcome`.
- `Plan`        : hành động agent đề xuất sau pha Think (tool + tham số).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class ToolOutcome:
    """Kết quả thực thi một tool - hình dạng tối giản, không phụ thuộc ORM."""

    name: str
    arguments: dict[str, Any]
    output: Any
    ok: bool
    error: str | None = None


@runtime_checkable
class ToolRunner(Protocol):
    """Cổng thực thi tool. Cài đặt thật: `app.tools.runner.ExecutorToolRunner`
    (SSH/Netmiko + GNS3 REST qua DB). Cài đặt giả lập cho test/demo:
    `app.agent_core.fakes.FakeToolRunner`."""

    def run(self, name: str, arguments: dict[str, Any]) -> ToolOutcome: ...


@dataclass
class Plan:
    """Hành động mà LLM đề xuất ở pha Think - chưa được thực thi."""

    tool: str
    arguments: dict[str, Any]
    node_id: str
    rationale: str = ""
