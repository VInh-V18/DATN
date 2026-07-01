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
