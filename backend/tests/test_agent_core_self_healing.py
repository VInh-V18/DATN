"""Kiểm chứng SelfHealingEngine (app.agent_core.self_healing) hoàn toàn bằng
LLM và thiết bị giả lập - không cần DB/GNS3/API key nào, chứng minh vòng lặp
Observe-Think-Act-Verify-Rollback và các guardrail hoạt động đúng cơ chế."""

from app.agent_core.fakes import FakeDevice, FakeInterface, FakeLLMClient, FakeToolRunner, InMemoryIncidentRecorder, ScriptedStep
from app.agent_core.self_healing import IncidentView, SelfHealingEngine


def _make_kb01_devices() -> dict[str, FakeDevice]:
    """Kịch bản KB01 (Bảng 5.2): cổng R2 nối R1 đang bị shutdown."""
    return {
        "R1": FakeDevice(id="R1", interfaces={"Gi0/0": FakeInterface(name="Gi0/0", status="up")}),
        "R2": FakeDevice(id="R2", interfaces={"Gi0/1": FakeInterface(name="Gi0/1", status="down")}),
    }


def test_kb01_full_success_resolves_incident() -> None:
    devices = _make_kb01_devices()
    tool_runner = FakeToolRunner(devices)
    llm = FakeLLMClient(
        [
            ScriptedStep(
                content="Cổng Gi0/1 trên R2 đang shutdown, tôi sẽ bật lại.",
                tool_calls=[("push_config", {"node_id": "R2", "config_lines": ["interface Gi0/1", "no shutdown"]})],
            )
        ]
    )
    recorder = InMemoryIncidentRecorder()
    engine = SelfHealingEngine(llm=llm, tool_runner=tool_runner, recorder=recorder, max_retries=3)

    incident = IncidentView(id="inc-1", description="R1 mất kết nối tới R2", device_ids=["R1", "R2"])
    outcome = engine.tu_khac_phuc(incident)

    assert outcome.status == "resolved"
    assert recorder.status["inc-1"] == "resolved"
    assert "inc-1" in recorder.resolved
    assert devices["R2"].interfaces["Gi0/1"].status == "up"
    assert len(recorder.actions) == 1
    assert recorder.actions[0][1] == "push_config"
    # Trạng thái phải đi qua đúng các pha: diagnosing -> remediating -> resolved.
    statuses = [event_status for _, event_status in recorder.events]
    assert statuses == ["diagnosing", "remediating", "resolved"]


def test_high_risk_action_requires_approval_then_executes_after_approval() -> None:
    devices = {"R1": FakeDevice(id="R1")}
    plan_tool_calls = [("block_ip", {"node_id": "R1", "ip_address": "203.0.113.9"})]
    recorder = InMemoryIncidentRecorder()

    # Lượt 1: chưa phê duyệt -> phải dừng lại chờ, KHÔNG được thực thi block_ip.
    llm1 = FakeLLMClient([ScriptedStep(content="Đề xuất chặn IP tấn công.", tool_calls=plan_tool_calls)])
    tool_runner = FakeToolRunner(devices)
    engine = SelfHealingEngine(llm=llm1, tool_runner=tool_runner, recorder=recorder, max_retries=3)
    incident = IncidentView(id="inc-2", description="Phát hiện quét cổng", device_ids=["R1"])

    outcome = engine.tu_khac_phuc(incident)

    assert outcome.status == "awaiting_approval"
    assert recorder.status["inc-2"] == "awaiting_approval"
    assert recorder.pending_action["inc-2"] == {
        "tool": "block_ip",
        "arguments": {"node_id": "R1", "ip_address": "203.0.113.9"},
        "approved": False,
    }
    assert recorder.actions == []  # guardrail phải chặn thực thi

    # Lượt 2: kỹ sư đã phê duyệt (mô phỏng POST /api/incidents/{id}/approve).
    llm2 = FakeLLMClient([ScriptedStep(content="Đề xuất chặn IP tấn công.", tool_calls=plan_tool_calls)])
    engine2 = SelfHealingEngine(llm=llm2, tool_runner=tool_runner, recorder=recorder, max_retries=3)
    approved_incident = IncidentView(
        id="inc-2",
        description="Phát hiện quét cổng",
        device_ids=["R1"],
        pending_action={"tool": "block_ip", "arguments": {"node_id": "R1", "ip_address": "203.0.113.9"}, "approved": True},
    )

    outcome2 = engine2.tu_khac_phuc(approved_incident)

    assert outcome2.status == "resolved"
    assert len(recorder.actions) == 1
    assert recorder.actions[0][1] == "block_ip"


def test_verify_failure_triggers_rollback_then_retry_succeeds() -> None:
    devices = _make_kb01_devices()
    tool_runner = FakeToolRunner(devices)
    recorder = InMemoryIncidentRecorder()
    llm = FakeLLMClient(
        [
            # Lần thử 1: agent đoán sai (chỉ chạy show, không thực sự bật lại cổng) -> verify thất bại -> rollback.
            ScriptedStep(content="Thử kiểm tra lại cấu hình.", tool_calls=[("send_command", {"node_id": "R2", "command": "show ip interface brief"})]),
            # Lần thử 2: agent sửa đúng -> verify thành công.
            ScriptedStep(content="Bật lại cổng.", tool_calls=[("push_config", {"node_id": "R2", "config_lines": ["interface Gi0/1", "no shutdown"]})]),
        ]
    )
    engine = SelfHealingEngine(llm=llm, tool_runner=tool_runner, recorder=recorder, max_retries=3)
    incident = IncidentView(id="inc-3", description="R1 mất kết nối tới R2", device_ids=["R1", "R2"])

    outcome = engine.tu_khac_phuc(incident)

    assert outcome.status == "resolved"
    assert len(recorder.actions) == 2
    assert recorder.actions[0][1] == "send_command"
    assert recorder.actions[1][1] == "push_config"
    assert ("rollback", {"node_id": "R2", "snapshot": "snapshot::R2"}) in [(c[0], c[1]) for c in tool_runner.calls]


def test_exhausts_retries_when_fix_never_verifies() -> None:
    devices = _make_kb01_devices()
    tool_runner = FakeToolRunner(devices)
    recorder = InMemoryIncidentRecorder()
    # Agent luôn đề xuất một lệnh không thực sự khắc phục được sự cố.
    llm = FakeLLMClient(
        [ScriptedStep(content="Thử lại.", tool_calls=[("send_command", {"node_id": "R2", "command": "show version"})])] * 3
    )
    engine = SelfHealingEngine(llm=llm, tool_runner=tool_runner, recorder=recorder, max_retries=3)
    incident = IncidentView(id="inc-4", description="R1 mất kết nối tới R2", device_ids=["R1", "R2"])

    outcome = engine.tu_khac_phuc(incident)

    assert outcome.status == "failed"
    assert outcome.detail == "can_can_thiep"
    assert recorder.status["inc-4"] == "failed"
    assert len(recorder.actions) == 3


def test_needs_intervention_when_llm_has_no_actionable_plan() -> None:
    devices = _make_kb01_devices()
    tool_runner = FakeToolRunner(devices)
    recorder = InMemoryIncidentRecorder()
    llm = FakeLLMClient([ScriptedStep(content="Tôi không chắc nguyên nhân là gì, cần kỹ sư kiểm tra thêm.")])
    engine = SelfHealingEngine(llm=llm, tool_runner=tool_runner, recorder=recorder, max_retries=3)
    incident = IncidentView(id="inc-5", description="Sự cố lạ", device_ids=["R1", "R2"])

    outcome = engine.tu_khac_phuc(incident)

    assert outcome.status == "failed"
    assert outcome.detail == "needs_intervention"
    assert recorder.actions == []


def test_static_guardrail_helpers() -> None:
    from app.agent_core.types import Plan

    assert SelfHealingEngine.duoc_phep("push_config") is True
    assert SelfHealingEngine.duoc_phep("delete_everything") is False

    assert SelfHealingEngine.rui_ro_cao(Plan(tool="block_ip", arguments={}, node_id="R1")) is True
    assert SelfHealingEngine.rui_ro_cao(Plan(tool="push_config", arguments={}, node_id="R1")) is False

    plan = Plan(tool="block_ip", arguments={}, node_id="R1")
    no_pending = IncidentView(id="x", description="", device_ids=[])
    assert SelfHealingEngine.cho_phe_duyet(no_pending, plan) is False

    approved = IncidentView(id="x", description="", device_ids=[], pending_action={"tool": "block_ip", "approved": True})
    assert SelfHealingEngine.cho_phe_duyet(approved, plan) is True

    wrong_tool = IncidentView(id="x", description="", device_ids=[], pending_action={"tool": "isolate_node", "approved": True})
    assert SelfHealingEngine.cho_phe_duyet(wrong_tool, plan) is False
