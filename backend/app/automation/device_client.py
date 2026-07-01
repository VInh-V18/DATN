"""Netmiko-based device automation.

Mắt xích giao thức thứ hai (mục 2.3, 2.5): mở phiên SSH/Telnet tới router/switch
trong GNS3 để đọc trạng thái và áp dụng cấu hình. Dùng cho các tool send_command,
push_config, get_interfaces, get_routing_table, ping_test, block_ip, isolate_node,
rollback (Bảng 3.3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from netmiko import ConnectHandler

from app.core.config import get_settings


@dataclass
class DeviceCredentials:
    host: str
    username: str
    password: str
    secret: str = ""
    device_type: str = "cisco_ios"
    port: int = 22
    timeout: int = 10

    @classmethod
    def for_device(cls, host: str, device_type: str | None = None) -> "DeviceCredentials":
        settings = get_settings()
        return cls(
            host=host,
            username=settings.device_ssh_username,
            password=settings.device_ssh_password,
            secret=settings.device_ssh_secret,
            device_type=device_type or settings.device_default_type,
            timeout=settings.device_ssh_timeout,
        )


@dataclass
class PingResult:
    success_rate: float
    rtt_avg_ms: float | None
    raw: str = field(repr=False, default="")


class DeviceClient:
    """Wrapper mỏng quanh Netmiko ConnectHandler, dùng như context manager."""

    def __init__(self, creds: DeviceCredentials) -> None:
        self._creds = creds
        self._conn = None

    def __enter__(self) -> "DeviceClient":
        self._conn = ConnectHandler(
            device_type=self._creds.device_type,
            host=self._creds.host,
            username=self._creds.username,
            password=self._creds.password,
            secret=self._creds.secret,
            port=self._creds.port,
            timeout=self._creds.timeout,
        )
        if self._creds.secret:
            self._conn.enable()
        return self

    def __exit__(self, *exc) -> None:
        if self._conn is not None:
            self._conn.disconnect()

    def send_command(self, command: str) -> str:
        return self._conn.send_command(command)

    def send_config_set(self, commands: list[str]) -> str:
        return self._conn.send_config_set(commands)

    def save_config_snapshot(self) -> str:
        """Trả về running-config hiện tại để dùng làm bản lưu cho rollback()."""
        return self._conn.send_command("show running-config")

    def restore_config_snapshot(self, snapshot: str) -> str:
        """Khôi phục cấu hình từ bản lưu (rollback) bằng cách nạp lại các dòng cấu hình."""
        lines = [line for line in snapshot.splitlines() if line.strip() and not line.startswith("!")]
        return self._conn.send_config_set(lines)

    def get_interfaces_status(self) -> list[dict]:
        output = self._conn.send_command("show ip interface brief")
        interfaces = []
        for line in output.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 6:
                interfaces.append(
                    {
                        "name": parts[0],
                        "ip_address": parts[1],
                        "status": parts[4],
                        "protocol": parts[5],
                    }
                )
        return interfaces

    def get_routing_table(self) -> str:
        return self._conn.send_command("show ip route")

    def read_logs(self, lines: int = 50) -> str:
        output = self._conn.send_command("show logging")
        return "\n".join(output.splitlines()[-lines:])

    def ping(self, target_ip: str, count: int = 5) -> PingResult:
        raw = self._conn.send_command(f"ping {target_ip} repeat {count}")
        match = re.search(r"Success rate is (\d+) percent.*?(?:round-trip.*?= [\d/]+/(\d+)/\d+)?", raw, re.DOTALL)
        success_rate = float(match.group(1)) / 100 if match else 0.0
        rtt_avg = float(match.group(2)) if match and match.group(2) else None
        return PingResult(success_rate=success_rate, rtt_avg_ms=rtt_avg, raw=raw)

    def shutdown_interface(self, interface_name: str) -> str:
        return self.send_config_set([f"interface {interface_name}", "shutdown"])

    def no_shutdown_interface(self, interface_name: str) -> str:
        return self.send_config_set([f"interface {interface_name}", "no shutdown"])

    def block_ip(self, ip_address: str, acl_name: str = "AGENT_BLOCK") -> str:
        """Áp ACL chặn một địa chỉ IP nguồn - dùng cho playbook an ninh (mục 3.3.4)."""
        commands = [
            f"ip access-list extended {acl_name}",
            f"deny ip host {ip_address} any",
            "permit ip any any",
        ]
        return self.send_config_set(commands)

    def isolate_node(self, management_interface: str | None = None) -> str:
        """Cô lập thiết bị bằng cách tắt toàn bộ cổng, trừ cổng quản lý (nếu có)."""
        interfaces = self.get_interfaces_status()
        results = []
        for iface in interfaces:
            if management_interface and iface["name"] == management_interface:
                continue
            results.append(self.shutdown_interface(iface["name"]))
        return "\n".join(results)
