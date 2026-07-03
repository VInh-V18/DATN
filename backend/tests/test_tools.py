from app.tools.executor import ToolExecutor
from app.tools.specs import TOOL_SPEC_BY_NAME, is_command_allowed


def test_all_tools_from_bang_3_3_present() -> None:
    expected = {
        "get_topology",
        "get_node_status",
        "get_interfaces",
        "read_logs",
        "get_metrics",
        "detect_anomaly",
        "start_node",
        "stop_node",
        "send_command",
        "push_config",
        "ping_test",
        "get_routing_table",
        "block_ip",
        "isolate_node",
        "rollback",
        "map_attack",
    }
    assert expected.issubset(TOOL_SPEC_BY_NAME.keys())


def test_command_whitelist() -> None:
    assert is_command_allowed("show ip interface brief")
    assert is_command_allowed("no shutdown")
    assert not is_command_allowed("reload")
    assert not is_command_allowed("write erase")


def test_high_risk_tools_flagged() -> None:
    assert TOOL_SPEC_BY_NAME["block_ip"].risk == "high"
    assert TOOL_SPEC_BY_NAME["isolate_node"].risk == "high"
    assert TOOL_SPEC_BY_NAME["get_topology"].read_only is True


class _UnusedDb:
    """DB giả không cho phép truy vấn nào - dùng để chứng minh chế độ dry-run
    không hề chạm tới thiết bị/DB cho các tool thay đổi hệ thống."""

    def get(self, *args, **kwargs):
        raise AssertionError("dry-run không được truy vấn DB cho tool thay đổi hệ thống")


class _UnusedGns3:
    def __getattr__(self, name):
        raise AssertionError("dry-run không được gọi GNS3 REST API cho tool thay đổi hệ thống")


def test_dry_run_send_command_does_not_touch_device() -> None:
    executor = ToolExecutor(db=_UnusedDb(), gns3_client=_UnusedGns3(), project_id="", dry_run=True)
    result = executor.execute("send_command", {"node_id": "R2", "command": "show ip interface brief"})
    assert result.ok is True
    assert result.output["dry_run"] is True
    assert result.output["would_execute"] == "show ip interface brief"


def test_dry_run_still_enforces_command_whitelist() -> None:
    executor = ToolExecutor(db=_UnusedDb(), gns3_client=_UnusedGns3(), project_id="", dry_run=True)
    result = executor.execute("send_command", {"node_id": "R2", "command": "reload"})
    assert result.ok is False
    assert "dry-run" in result.error.lower()


def test_dry_run_push_config_rejects_disallowed_line() -> None:
    executor = ToolExecutor(db=_UnusedDb(), gns3_client=_UnusedGns3(), project_id="", dry_run=True)
    result = executor.execute("push_config", {"node_id": "R2", "config_lines": ["no shutdown", "write erase"]})
    assert result.ok is False


def test_dry_run_simulates_high_risk_tools_without_touching_device() -> None:
    executor = ToolExecutor(db=_UnusedDb(), gns3_client=_UnusedGns3(), project_id="", dry_run=True)
    result = executor.execute("block_ip", {"node_id": "R1", "ip_address": "10.0.0.9"})
    assert result.ok is True
    assert result.output == {"dry_run": True, "would_execute": "block_ip({'node_id': 'R1', 'ip_address': '10.0.0.9'})"}


def test_dry_run_does_not_affect_read_only_tools() -> None:
    class _Gns3Stub:
        def get_topology(self, project_id: str) -> dict:
            return {"nodes": [], "links": []}

    executor = ToolExecutor(db=_UnusedDb(), gns3_client=_Gns3Stub(), project_id="proj1", dry_run=True)
    result = executor.execute("get_topology", {})
    assert result.ok is True
    assert result.output == {"nodes": [], "links": []}
