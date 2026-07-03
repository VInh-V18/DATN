"""Tool Executor - mục 3.2.2, 3.4.

Thực thi lời gọi công cụ mà LLM chọn: hoặc gọi GNS3 REST API (qua GNS3Client),
hoặc mở phiên SSH tới thiết bị (qua DeviceClient). Đây là nơi guardrails về
danh sách lệnh cho phép được áp dụng trước khi chạm vào hệ thống thật.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.automation.device_client import DeviceClient, DeviceCredentials
from app.gns3.client import GNS3Client
from app.models.models import Device
from app.tools.specs import TOOL_SPEC_BY_NAME, is_command_allowed


class ToolError(RuntimeError):
    pass


class GuardrailViolation(ToolError):
    """Lệnh không nằm trong danh sách cho phép hoặc hành động không được đăng ký."""


@dataclass
class ToolResult:
    name: str
    arguments: dict[str, Any]
    output: Any
    ok: bool
    error: str | None = None


class ToolExecutor:
    """dry_run=True mô phỏng mọi tool THAY ĐỔI HỆ THỐNG (guardrail "chạy thử
    trước khi áp dụng khi có thể", mục 3.3.2): guardrail lệnh cho phép vẫn
    được áp dụng đầy đủ, nhưng KHÔNG mở phiên SSH hay gọi GNS3 REST API thật -
    chỉ trả về kết quả mô phỏng để kỹ sư xem trước hành động agent định làm.
    Các tool chỉ đọc luôn chạy thật kể cả ở chế độ dry-run (không có gì để
    mô phỏng, và cần dữ liệu thật cho pha Observe/Think).
    """

    def __init__(self, db: Session, gns3_client: GNS3Client, project_id: str, dry_run: bool = False) -> None:
        self.db = db
        self.gns3 = gns3_client
        self.project_id = project_id
        self.dry_run = dry_run

    def _device(self, node_id: str) -> Device:
        device = self.db.get(Device, node_id)
        if device is None:
            raise ToolError(f"Không tìm thấy thiết bị {node_id}")
        return device

    def _device_client(self, node_id: str) -> DeviceClient:
        device = self._device(node_id)
        if not device.management_address:
            raise ToolError(f"Thiết bị {node_id} chưa có địa chỉ quản lý để kết nối SSH")
        creds = DeviceCredentials.for_device(device.management_address)
        return DeviceClient(creds)

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        spec = TOOL_SPEC_BY_NAME.get(name)
        if spec is None:
            raise GuardrailViolation(f"Tool '{name}' không nằm trong danh sách công cụ được phép")
        try:
            if self.dry_run and not spec.read_only:
                output = self._dry_run(name, arguments)
            else:
                output = self._dispatch(name, arguments)
            return ToolResult(name=name, arguments=arguments, output=output, ok=True)
        except ToolError as exc:
            return ToolResult(name=name, arguments=arguments, output=None, ok=False, error=str(exc))

    def _dispatch(self, name: str, args: dict[str, Any]) -> Any:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            raise ToolError(f"Chưa hiện thực tool '{name}'")
        return handler(**args)

    def _dry_run(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Áp guardrail lệnh cho phép như bình thường, nhưng không chạm vào
        thiết bị/GNS3 thật - chỉ trả về hành động sẽ được thực hiện."""
        if name == "send_command":
            command = arguments.get("command", "")
            if not is_command_allowed(command):
                raise GuardrailViolation(f"[dry-run] Câu lệnh '{command}' không nằm trong danh sách cho phép")
            return {"dry_run": True, "would_execute": command}

        if name == "push_config":
            for line in arguments.get("config_lines", []):
                if not is_command_allowed(line):
                    raise GuardrailViolation(f"[dry-run] Dòng cấu hình '{line}' không nằm trong danh sách cho phép")
            return {"dry_run": True, "would_execute": arguments.get("config_lines", [])}

        return {"dry_run": True, "would_execute": f"{name}({arguments})"}

    # --- Giám sát ---

    def _tool_get_topology(self, project_id: str | None = None) -> dict:
        return self.gns3.get_topology(project_id or self.project_id)

    def _tool_get_node_status(self, node_id: str) -> dict:
        device = self._device(node_id)
        if device.gns3_node_id:
            return self.gns3.get_node(self.project_id, device.gns3_node_id)
        raise ToolError(f"Thiết bị {node_id} chưa liên kết với node GNS3")

    def _tool_get_interfaces(self, node_id: str) -> list[dict]:
        with self._device_client(node_id) as dc:
            return dc.get_interfaces_status()

    def _tool_read_logs(self, node_id: str, lines: int = 50) -> str:
        with self._device_client(node_id) as dc:
            return dc.read_logs(lines=lines)

    def _tool_get_metrics(self, node_id: str, time_range: str = "-15m") -> list[dict]:
        from app.monitoring.influx_client import InfluxMetricsStore

        return InfluxMetricsStore().query_metrics(device_id=node_id, time_range=time_range)

    def _tool_detect_anomaly(self, series: list[list[float]]) -> dict:
        from app.monitoring.anomaly import AnomalyDetector

        detector = AnomalyDetector()
        return detector.score(series)

    # --- Tự khắc phục ---

    def _tool_start_node(self, node_id: str) -> dict:
        device = self._device(node_id)
        return self.gns3.start_node(self.project_id, device.gns3_node_id)

    def _tool_stop_node(self, node_id: str) -> dict:
        device = self._device(node_id)
        return self.gns3.stop_node(self.project_id, device.gns3_node_id)

    def _tool_send_command(self, node_id: str, command: str) -> str:
        if not is_command_allowed(command):
            raise GuardrailViolation(f"Câu lệnh '{command}' không nằm trong danh sách cho phép")
        with self._device_client(node_id) as dc:
            return dc.send_command(command)

    def _tool_push_config(self, node_id: str, config_lines: list[str]) -> str:
        for line in config_lines:
            if not is_command_allowed(line):
                raise GuardrailViolation(f"Dòng cấu hình '{line}' không nằm trong danh sách cho phép")
        with self._device_client(node_id) as dc:
            return dc.send_config_set(config_lines)

    def _tool_ping_test(self, source_node_id: str, target_node_id: str) -> dict:
        target_device = self._device(target_node_id)
        if not target_device.management_address:
            raise ToolError(f"Thiết bị đích {target_node_id} chưa có địa chỉ quản lý")
        with self._device_client(source_node_id) as dc:
            result = dc.ping(target_device.management_address)
            return {"success_rate": result.success_rate, "rtt_avg_ms": result.rtt_avg_ms}

    def _tool_get_routing_table(self, node_id: str) -> str:
        with self._device_client(node_id) as dc:
            return dc.get_routing_table()

    def _tool_rollback(self, node_id: str, snapshot: str) -> str:
        with self._device_client(node_id) as dc:
            return dc.restore_config_snapshot(snapshot)

    # --- An ninh ---

    def _tool_block_ip(self, node_id: str, ip_address: str) -> str:
        with self._device_client(node_id) as dc:
            return dc.block_ip(ip_address)

    def _tool_isolate_node(self, node_id: str) -> str:
        with self._device_client(node_id) as dc:
            return dc.isolate_node()

    def _tool_map_attack(self, indicators: list[str]) -> list[dict]:
        from app.security.attack_mapping import map_indicators

        return map_indicators(indicators)
