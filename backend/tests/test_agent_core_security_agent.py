"""Kiểm chứng SecurityAgent (app.agent_core.security_agent) - pha LLM Think
xác nhận + tự chọn hành động phản ứng (Hình 3.7) - bằng LLM và thiết bị giả
lập, không cần API key."""

from app.agent_core.fakes import FakeDevice, FakeInterface, FakeLLMClient, FakeToolRunner, InMemorySecurityRecorder, ScriptedStep
from app.agent_core.security_agent import DetectionView, SecurityAgent


def test_high_risk_response_requires_approval_then_executes() -> None:
    tool_runner = FakeToolRunner({"R1": FakeDevice(id="R1")})
    recorder = InMemorySecurityRecorder()
    llm = FakeLLMClient(
        [ScriptedStep(content="Xác nhận dò mật khẩu SSH, đề xuất chặn IP nguồn.", tool_calls=[("block_ip", {"node_id": "R1", "ip_address": "10.0.0.9"})])]
    )
    agent = SecurityAgent(llm=llm, tool_runner=tool_runner, recorder=recorder)
    detection = DetectionView(indicator="ssh_bruteforce", source_ip="10.0.0.9", detail={"failed_attempts": 6}, edge_node_id="R1")

    outcome = agent.handle(detection)

    assert outcome.status == "awaiting_approval"
    assert recorder.alerts[outcome.alert_id]["status"] == "awaiting_approval"
    assert recorder.attack_mappings[outcome.alert_id][0]["technique_id"] == "T1110"
    assert recorder.pending_action[outcome.alert_id] == {"tool": "block_ip", "arguments": {"node_id": "R1", "ip_address": "10.0.0.9"}}
    assert tool_runner.calls == []  # guardrail: chưa duyệt thì chưa thực thi

    outcome2 = agent.approve(outcome.alert_id, recorder.pending_action[outcome.alert_id])

    assert outcome2.status == "blocked"
    assert recorder.alerts[outcome.alert_id]["status"] == "blocked"
    assert [c[0] for c in tool_runner.calls] == ["block_ip"]


def test_llm_chooses_isolate_node_for_syn_flood_when_auto_approved() -> None:
    devices = {"R1": FakeDevice(id="R1", interfaces={"Gi0/0": FakeInterface(name="Gi0/0", status="up")})}
    tool_runner = FakeToolRunner(devices)
    recorder = InMemorySecurityRecorder()
    llm = FakeLLMClient(
        [ScriptedStep(content="SYN flood mức độ nghiêm trọng, cô lập thiết bị ngay.", tool_calls=[("isolate_node", {"node_id": "R1"})])]
    )
    agent = SecurityAgent(llm=llm, tool_runner=tool_runner, recorder=recorder)
    detection = DetectionView(indicator="syn_flood", source_ip="198.51.100.4", detail={"half_open_count": 300}, edge_node_id="R1")

    outcome = agent.handle(detection, auto_approved=True)

    assert outcome.status == "blocked"
    assert devices["R1"].interfaces["Gi0/0"].status == "down"
    assert recorder.alerts[outcome.alert_id]["severity"] == "high"


def test_no_edge_device_only_creates_alert() -> None:
    tool_runner = FakeToolRunner({})
    recorder = InMemorySecurityRecorder()
    llm = FakeLLMClient([])
    agent = SecurityAgent(llm=llm, tool_runner=tool_runner, recorder=recorder)
    detection = DetectionView(indicator="port_scan", source_ip="203.0.113.9", detail={"distinct_ports": 20}, edge_node_id=None)

    outcome = agent.handle(detection)

    assert outcome.status == "alert_only"
    assert recorder.alerts[outcome.alert_id]["status"] == "alert_only"
    assert llm.chat_calls == []  # không cần suy luận khi không có gì để phản ứng


def test_llm_declines_to_act_results_in_alert_only() -> None:
    tool_runner = FakeToolRunner({"R1": FakeDevice(id="R1")})
    recorder = InMemorySecurityRecorder()
    llm = FakeLLMClient([ScriptedStep(content="Chưa đủ bằng chứng để khẳng định đây là tấn công thật.")])
    agent = SecurityAgent(llm=llm, tool_runner=tool_runner, recorder=recorder)
    detection = DetectionView(indicator="port_scan", source_ip="203.0.113.9", detail={"distinct_ports": 16}, edge_node_id="R1")

    outcome = agent.handle(detection)

    assert outcome.status == "alert_only"
    assert tool_runner.calls == []
