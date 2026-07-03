"""Kiểm chứng CopilotEngine (app.agent_core.copilot) - tách bạch đọc/ghi
(mục 3.3.3) - bằng LLM và thiết bị giả lập, không cần API key."""

from app.agent_core.copilot import CopilotEngine, SYSTEM_PROMPT, is_confirmation
from app.agent_core.fakes import FakeDevice, FakeInterface, FakeLLMClient, FakeToolRunner, ScriptedStep


def _messages(user_message: str) -> list[dict]:
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_message}]


def test_read_only_question_synthesizes_answer_after_tool_call() -> None:
    devices = {"R2": FakeDevice(id="R2", interfaces={"Gi0/1": FakeInterface(name="Gi0/1", status="down")})}
    tool_runner = FakeToolRunner(devices)
    llm = FakeLLMClient(
        [
            ScriptedStep(content="Để tôi kiểm tra bảng định tuyến trên R2.", tool_calls=[("get_routing_table", {"node_id": "R2"})]),
            ScriptedStep(content="Trên R2, tuyến tới mạng R1 đang thiếu - khả năng OSPF bị gián đoạn."),
        ]
    )
    engine = CopilotEngine(llm=llm, tool_runner=tool_runner)

    turn = engine.ask(_messages("Vì sao R1 không kết nối được tới R2?"))

    assert turn.requires_confirmation is False
    assert turn.pending_action is None
    assert "OSPF" in turn.text
    assert len(turn.tool_calls) == 1
    assert turn.tool_calls[0]["name"] == "get_routing_table"
    assert ("get_routing_table", {"node_id": "R2"}) in [(c[0], c[1]) for c in tool_runner.calls]


def test_state_changing_proposal_requires_confirmation_and_does_not_execute() -> None:
    devices = {"R2": FakeDevice(id="R2", interfaces={"Gi0/1": FakeInterface(name="Gi0/1", status="down")})}
    tool_runner = FakeToolRunner(devices)
    llm = FakeLLMClient(
        [
            ScriptedStep(
                content="",
                tool_calls=[("push_config", {"node_id": "R2", "config_lines": ["interface Gi0/1", "no shutdown"]})],
            )
        ]
    )
    engine = CopilotEngine(llm=llm, tool_runner=tool_runner)

    turn = engine.ask(_messages("Bật lại cổng Gi0/1 trên R2 giúp tôi."))

    assert turn.requires_confirmation is True
    assert turn.pending_action == {"tool": "push_config", "arguments": {"node_id": "R2", "config_lines": ["interface Gi0/1", "no shutdown"]}}
    # Chưa được xác nhận thì chưa được thực thi - cổng phải vẫn đang down.
    assert devices["R2"].interfaces["Gi0/1"].status == "down"
    assert tool_runner.calls == []


def test_confirm_executes_the_pending_action() -> None:
    devices = {"R2": FakeDevice(id="R2", interfaces={"Gi0/1": FakeInterface(name="Gi0/1", status="down")})}
    tool_runner = FakeToolRunner(devices)
    engine = CopilotEngine(llm=FakeLLMClient([]), tool_runner=tool_runner)

    pending_action = {"tool": "push_config", "arguments": {"node_id": "R2", "config_lines": ["interface Gi0/1", "no shutdown"]}}
    turn = engine.confirm(pending_action)

    assert turn.requires_confirmation is False
    assert turn.pending_action is None
    assert devices["R2"].interfaces["Gi0/1"].status == "up"
    assert "Đã thực hiện" in turn.text


def test_is_confirmation_positive_and_negative_cases() -> None:
    assert is_confirmation("có") is True
    assert is_confirmation("Đồng ý, thực hiện đi") is True
    assert is_confirmation("yes") is True

    assert is_confirmation("không") is False
    assert is_confirmation("không đồng ý") is False  # không được khớp nhầm "đồng ý" bên trong câu phủ định
    assert is_confirmation("chỉ báo cáo, đừng tự sửa") is False
