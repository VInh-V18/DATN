"""Đặc tả các tool của agent (Bảng 3.3).

Mỗi tool ánh xạ tới một thao tác cụ thể trên hệ thống: một lời gọi GNS3 REST API
hoặc một phiên SSH tới thiết bị. `risk` và `read_only` phục vụ cơ chế guardrails
(mục 3.3.2): hành động rủi ro cao bắt buộc phải được kỹ sư phê duyệt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Risk = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    read_only: bool
    risk: Risk


TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_topology",
        description="Lấy danh sách node, liên kết và trạng thái của toàn bộ topology mạng.",
        parameters={
            "type": "object",
            "properties": {"project_id": {"type": "string", "description": "Định danh dự án GNS3"}},
            "required": ["project_id"],
        },
        read_only=True,
        risk="low",
    ),
    ToolSpec(
        name="get_node_status",
        description="Lấy trạng thái chạy/dừng và thông tin cổng của một thiết bị.",
        parameters={
            "type": "object",
            "properties": {"node_id": {"type": "string", "description": "Định danh thiết bị"}},
            "required": ["node_id"],
        },
        read_only=True,
        risk="low",
    ),
    ToolSpec(
        name="get_interfaces",
        description="Lấy danh sách interface và trạng thái up/down của một thiết bị.",
        parameters={
            "type": "object",
            "properties": {"node_id": {"type": "string"}},
            "required": ["node_id"],
        },
        read_only=True,
        risk="low",
    ),
    ToolSpec(
        name="read_logs",
        description="Đọc nhật ký/console gần nhất của thiết bị.",
        parameters={
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "lines": {"type": "integer", "description": "Số dòng cần đọc", "default": 50},
            },
            "required": ["node_id"],
        },
        read_only=True,
        risk="low",
    ),
    ToolSpec(
        name="get_metrics",
        description="Truy vấn số liệu CPU, băng thông, tỉ lệ rớt gói của thiết bị theo khoảng thời gian.",
        parameters={
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "time_range": {"type": "string", "description": "Khoảng thời gian, ví dụ '-15m'", "default": "-15m"},
            },
            "required": ["node_id"],
        },
        read_only=True,
        risk="low",
    ),
    ToolSpec(
        name="detect_anomaly",
        description="Đưa một chuỗi số liệu vào mô hình Isolation Forest và trả về kết luận có/không bất thường.",
        parameters={
            "type": "object",
            "properties": {
                "series": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                    "description": "Danh sách vector đặc trưng theo thời gian",
                }
            },
            "required": ["series"],
        },
        read_only=True,
        risk="low",
    ),
    ToolSpec(
        name="start_node",
        description="Khởi động một thiết bị trong GNS3.",
        parameters={
            "type": "object",
            "properties": {"node_id": {"type": "string"}},
            "required": ["node_id"],
        },
        read_only=False,
        risk="medium",
    ),
    ToolSpec(
        name="stop_node",
        description="Dừng một thiết bị trong GNS3.",
        parameters={
            "type": "object",
            "properties": {"node_id": {"type": "string"}},
            "required": ["node_id"],
        },
        read_only=False,
        risk="medium",
    ),
    ToolSpec(
        name="send_command",
        description="Gửi một câu lệnh CLI tới thiết bị qua SSH và trả về kết quả.",
        parameters={
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "Định danh thiết bị trong GNS3"},
                "command": {"type": "string", "description": "Câu lệnh cần thực thi trên thiết bị"},
            },
            "required": ["node_id", "command"],
        },
        read_only=False,
        risk="medium",
    ),
    ToolSpec(
        name="push_config",
        description="Áp dụng một khối cấu hình lên thiết bị.",
        parameters={
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "config_lines": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["node_id", "config_lines"],
        },
        read_only=False,
        risk="medium",
    ),
    ToolSpec(
        name="ping_test",
        description="Kiểm chứng kết nối giữa hai thiết bị, trả về tỉ lệ gói thành công và RTT.",
        parameters={
            "type": "object",
            "properties": {
                "source_node_id": {"type": "string", "description": "Định danh thiết bị nguồn"},
                "target_node_id": {"type": "string", "description": "Định danh thiết bị đích"},
            },
            "required": ["source_node_id", "target_node_id"],
        },
        read_only=True,
        risk="low",
    ),
    ToolSpec(
        name="get_routing_table",
        description="Lấy bảng định tuyến của thiết bị.",
        parameters={
            "type": "object",
            "properties": {"node_id": {"type": "string"}},
            "required": ["node_id"],
        },
        read_only=True,
        risk="low",
    ),
    ToolSpec(
        name="block_ip",
        description="Áp ACL chặn một địa chỉ IP nguồn trên thiết bị biên.",
        parameters={
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "ip_address": {"type": "string"},
            },
            "required": ["node_id", "ip_address"],
        },
        read_only=False,
        risk="high",
    ),
    ToolSpec(
        name="isolate_node",
        description="Cô lập một thiết bị bằng cách tắt toàn bộ cổng của nó.",
        parameters={
            "type": "object",
            "properties": {"node_id": {"type": "string"}},
            "required": ["node_id"],
        },
        read_only=False,
        risk="high",
    ),
    ToolSpec(
        name="rollback",
        description="Khôi phục cấu hình thiết bị từ một bản lưu trước đó.",
        parameters={
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "snapshot": {"type": "string", "description": "Nội dung cấu hình đã lưu trước đó"},
            },
            "required": ["node_id", "snapshot"],
        },
        read_only=False,
        risk="medium",
    ),
    ToolSpec(
        name="map_attack",
        description="Ánh xạ tập dấu hiệu tấn công sang kỹ thuật và chiến thuật MITRE ATT&CK.",
        parameters={
            "type": "object",
            "properties": {
                "indicators": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Danh sách dấu hiệu, ví dụ ['port_scan', 'ssh_bruteforce']",
                }
            },
            "required": ["indicators"],
        },
        read_only=True,
        risk="low",
    ),
]

TOOL_SPEC_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_SPECS}

READ_ONLY_TOOL_NAMES = {spec.name for spec in TOOL_SPECS if spec.read_only}

# Guardrail: danh sách lệnh CLI được kiểm duyệt cho send_command / push_config (mục 3.3.2).
ALLOWED_CLI_COMMAND_PREFIXES = [
    "show ",
    "ping ",
    "traceroute ",
    "interface ",
    "shutdown",
    "no shutdown",
    "ip address ",
    "no ip address",
    "router ospf",
    "network ",
    "ip route ",
    "no ip route ",
    "ip access-list",
    "deny ",
    "permit ",
    "access-group ",
    "mtu ",
    "ip mtu ",
    "exit",
    "end",
]


def is_command_allowed(command: str) -> bool:
    normalized = command.strip().lower()
    return any(normalized.startswith(prefix) for prefix in ALLOWED_CLI_COMMAND_PREFIXES)
