"""Gây lỗi chủ động (fault injection) - Bảng 5.2, mục 5.2 và GĐ6 (Bảng 5.4).

Mười kịch bản KB01-KB10 dùng để đánh giá khách quan năng lực tự khắc phục và
phản ứng an ninh của agent (Bảng 5.3): script này chủ động tạo ra sự cố/tấn
công trên lab GNS3 thật, sau đó quan sát xem agent (chạy qua backend) có tự
phát hiện và xử lý đúng như "Hành vi kỳ vọng" ở Bảng 5.2 hay không.

Vì tên interface thực tế phụ thuộc vào loại thiết bị/template GNS3 đang dùng
(ví dụ GigabitEthernet0/1 trên Cisco IOSv, Ethernet0/1 trên IOU...), các kịch
bản liên quan tới cổng nhận `--interface` làm tham số thay vì đoán cứng.

Sử dụng:
    python -m scripts.fault_injection list
    python -m scripts.fault_injection KB01 --device R2 --interface GigabitEthernet0/1
    python -m scripts.fault_injection KB08 --attacker ATTACKER --target R1
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from app.automation.device_client import DeviceClient, DeviceCredentials
from app.core.database import SessionLocal
from app.models.models import Device

SCENARIOS = {
    "KB01": "Cấu hình - Cổng kết nối bị shutdown. Kỳ vọng: agent phát hiện, áp 'no shutdown', ping kiểm chứng.",
    "KB02": "Cấu hình - Sai địa chỉ IP trên interface. Kỳ vọng: agent phát hiện sai khác, cấu hình lại đúng.",
    "KB03": "Định tuyến - Thiếu/sai tuyến OSPF. Kỳ vọng: agent khôi phục cấu hình OSPF, kiểm chứng kết nối.",
    "KB04": "Định tuyến - Sai MTU gây rớt gói lớn. Kỳ vọng: agent phát hiện và chỉnh lại MTU.",
    "KB05": "ACL - ACL chặn nhầm lưu lượng hợp lệ. Kỳ vọng: agent nhận diện và gỡ/điều chỉnh ACL.",
    "KB06": "Liên kết - Liên kết chập chờn (link flap). Kỳ vọng: agent phát hiện bất thường, cảnh báo và ổn định.",
    "KB07": "Dịch vụ - Dịch vụ trên máy chủ ngừng hoạt động. Kỳ vọng: agent phát hiện và khởi động lại dịch vụ.",
    "KB08": "An ninh - Quét cổng từ máy tấn công. Kỳ vọng: agent phát hiện, ánh xạ ATT&CK, chặn IP nguồn.",
    "KB09": "An ninh - Tấn công DoS SYN flood. Kỳ vọng: agent phát hiện, áp rate-limit/ACL, cảnh báo.",
    "KB10": "An ninh - Dò mật khẩu SSH (brute-force). Kỳ vọng: agent phát hiện, chặn IP nguồn, cảnh báo.",
}


@dataclass
class InjectionResult:
    scenario: str
    detail: str


def _device_client_for(name: str) -> DeviceClient:
    db = SessionLocal()
    try:
        device = db.query(Device).filter_by(name=name).first()
        if device is None or not device.management_address:
            raise RuntimeError(f"Thiết bị '{name}' chưa được seed vào DB hoặc chưa có management_address")
        return DeviceClient(DeviceCredentials.for_device(device.management_address))
    finally:
        db.close()


# --- KB01-KB07: sự cố vận hành, thao tác trực tiếp qua Netmiko (bỏ qua guardrail của agent) ---


def inject_kb01(device: str, interface: str) -> InjectionResult:
    with _device_client_for(device) as dc:
        dc.shutdown_interface(interface)
    return InjectionResult("KB01", f"Đã shutdown {interface} trên {device}")


def inject_kb02(device: str, interface: str, wrong_ip: str, wrong_mask: str = "255.255.255.0") -> InjectionResult:
    with _device_client_for(device) as dc:
        dc.send_config_set([f"interface {interface}", f"ip address {wrong_ip} {wrong_mask}"])
    return InjectionResult("KB02", f"Đã đặt sai IP {wrong_ip} trên {interface} của {device}")


def inject_kb03(device: str, network: str, wildcard: str, area: int = 0) -> InjectionResult:
    with _device_client_for(device) as dc:
        dc.send_config_set(["router ospf 1", f"no network {network} {wildcard} area {area}"])
    return InjectionResult("KB03", f"Đã gỡ tuyến OSPF {network} {wildcard} area {area} trên {device}")


def inject_kb04(device: str, interface: str, wrong_mtu: int = 500) -> InjectionResult:
    with _device_client_for(device) as dc:
        dc.send_config_set([f"interface {interface}", f"ip mtu {wrong_mtu}"])
    return InjectionResult("KB04", f"Đã đặt sai MTU={wrong_mtu} trên {interface} của {device}")


def inject_kb05(device: str, blocked_network: str, wildcard: str, interface: str, acl_name: str = "FAULT_ACL") -> InjectionResult:
    with _device_client_for(device) as dc:
        dc.send_config_set(
            [
                f"ip access-list extended {acl_name}",
                f"deny ip {blocked_network} {wildcard} any",
                "permit ip any any",
                f"interface {interface}",
                f"ip access-group {acl_name} in",
            ]
        )
    return InjectionResult("KB05", f"Đã áp ACL '{acl_name}' chặn nhầm {blocked_network} trên {device}/{interface}")


def inject_kb06(device: str, interface: str, flaps: int = 5, delay_seconds: float = 2.0) -> InjectionResult:
    import time

    with _device_client_for(device) as dc:
        for _ in range(flaps):
            dc.shutdown_interface(interface)
            time.sleep(delay_seconds)
            dc.no_shutdown_interface(interface)
            time.sleep(delay_seconds)
    return InjectionResult("KB06", f"Đã gây link-flap {flaps} lần trên {interface} của {device}")


def inject_kb07(device: str, service_name: str) -> InjectionResult:
    """Dừng một dịch vụ trên máy chủ (ví dụ AGENT_SERVER) - thực thi qua SSH/shell (không phải Cisco CLI)."""
    with _device_client_for(device) as dc:
        dc._conn.send_command(f"sudo systemctl stop {service_name}")  # noqa: SLF001 - host chạy Linux, không phải Cisco IOS
    return InjectionResult("KB07", f"Đã dừng dịch vụ '{service_name}' trên {device}")


# --- KB08-KB10: tấn công an ninh, thực thi từ máy tấn công (ATTACKER) ---


def inject_kb08(attacker: str, target: str, target_ip: str, port_range: str = "1-1000") -> InjectionResult:
    with _device_client_for(attacker) as dc:
        dc._conn.send_command(f"nmap -p {port_range} -T4 {target_ip}", read_timeout=60)  # noqa: SLF001
    return InjectionResult("KB08", f"Đã quét cổng {target_ip} ({target}) dải {port_range} từ {attacker}")


def inject_kb09(attacker: str, target_ip: str, duration_seconds: int = 20) -> InjectionResult:
    with _device_client_for(attacker) as dc:
        dc._conn.send_command(  # noqa: SLF001
            f"sudo hping3 -S -p 80 --flood {target_ip} &\nsleep {duration_seconds}\nsudo pkill hping3",
            read_timeout=duration_seconds + 10,
        )
    return InjectionResult("KB09", f"Đã sinh SYN flood {duration_seconds}s tới {target_ip} từ {attacker}")


def inject_kb10(attacker: str, target_ip: str, username: str = "admin", wordlist: str = "/usr/share/wordlists/rockyou.txt") -> InjectionResult:
    with _device_client_for(attacker) as dc:
        dc._conn.send_command(  # noqa: SLF001
            f"hydra -l {username} -P {wordlist} -t 4 {target_ip} ssh", read_timeout=120
        )
    return InjectionResult("KB10", f"Đã dò mật khẩu SSH trên {target_ip} (user={username}) từ {attacker}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="scenario", required=True)

    sub.add_parser("list")

    p = sub.add_parser("KB01")
    p.add_argument("--device", required=True)
    p.add_argument("--interface", required=True)

    p = sub.add_parser("KB02")
    p.add_argument("--device", required=True)
    p.add_argument("--interface", required=True)
    p.add_argument("--wrong-ip", required=True)
    p.add_argument("--wrong-mask", default="255.255.255.0")

    p = sub.add_parser("KB03")
    p.add_argument("--device", required=True)
    p.add_argument("--network", required=True)
    p.add_argument("--wildcard", required=True)
    p.add_argument("--area", type=int, default=0)

    p = sub.add_parser("KB04")
    p.add_argument("--device", required=True)
    p.add_argument("--interface", required=True)
    p.add_argument("--wrong-mtu", type=int, default=500)

    p = sub.add_parser("KB05")
    p.add_argument("--device", required=True)
    p.add_argument("--interface", required=True)
    p.add_argument("--blocked-network", required=True)
    p.add_argument("--wildcard", required=True)

    p = sub.add_parser("KB06")
    p.add_argument("--device", required=True)
    p.add_argument("--interface", required=True)
    p.add_argument("--flaps", type=int, default=5)

    p = sub.add_parser("KB07")
    p.add_argument("--device", required=True)
    p.add_argument("--service-name", required=True)

    p = sub.add_parser("KB08")
    p.add_argument("--attacker", default="ATTACKER")
    p.add_argument("--target", required=True)
    p.add_argument("--target-ip", required=True)
    p.add_argument("--port-range", default="1-1000")

    p = sub.add_parser("KB09")
    p.add_argument("--attacker", default="ATTACKER")
    p.add_argument("--target-ip", required=True)
    p.add_argument("--duration-seconds", type=int, default=20)

    p = sub.add_parser("KB10")
    p.add_argument("--attacker", default="ATTACKER")
    p.add_argument("--target-ip", required=True)
    p.add_argument("--username", default="admin")
    p.add_argument("--wordlist", default="/usr/share/wordlists/rockyou.txt")

    args = parser.parse_args()

    if args.scenario == "list":
        for code, desc in SCENARIOS.items():
            print(f"{code}: {desc}")
        return

    kwargs = {k: v for k, v in vars(args).items() if k != "scenario"}
    handler = globals()[f"inject_{args.scenario.lower()}"]
    result = handler(**kwargs)
    print(f"[{result.scenario}] {result.detail}")


if __name__ == "__main__":
    sys.exit(main())
