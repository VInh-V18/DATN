"""Demo lõi AI Agent (app.agent_core) chạy độc lập - KHÔNG cần API key
(Ollama/Claude), KHÔNG cần GNS3 hay PostgreSQL. Dùng để minh hoạ trực quan
vòng lặp Observe-Think-Act-Verify-Rollback (mục 3.3.2) và Copilot (mục 3.3.3)
hoạt động đúng cơ chế, bằng một LLM giả lập (FakeLLMClient) phát lại kịch bản
định trước và một "mạng" tối giản trong bộ nhớ (FakeToolRunner).

Sử dụng:
    python -m scripts.demo_agent self-healing   # kịch bản KB01 (Bảng 5.2)
    python -m scripts.demo_agent copilot        # hỏi đáp + đề xuất hành động
    python -m scripts.demo_agent all            # chạy cả hai (mặc định)
"""

from __future__ import annotations

import sys

from app.agent_core.copilot import CopilotEngine, SYSTEM_PROMPT as COPILOT_SYSTEM_PROMPT
from app.agent_core.fakes import (
    FakeDevice,
    FakeInterface,
    FakeLLMClient,
    FakeToolRunner,
    InMemoryIncidentRecorder,
    ScriptedStep,
)
from app.agent_core.self_healing import IncidentView, SelfHealingEngine

RULE = "-" * 72


def _print_header(title: str) -> None:
    print(f"\n{RULE}\n{title}\n{RULE}")


def demo_self_healing() -> None:
    _print_header("KỊCH BẢN KB01 (Bảng 5.2): cổng R2-R1 bị shutdown")

    devices = {
        "R1": FakeDevice(id="R1", interfaces={"Gi0/0": FakeInterface(name="Gi0/0", status="up")}),
        "R2": FakeDevice(id="R2", interfaces={"Gi0/1": FakeInterface(name="Gi0/1", status="down")}),
    }
    print("Trạng thái ban đầu: R2/Gi0/1 = DOWN -> R1 không ping được R2\n")

    tool_runner = FakeToolRunner(devices)
    llm = FakeLLMClient(
        [
            ScriptedStep(
                content="Quan sát cho thấy cổng Gi0/1 trên R2 đang ở trạng thái down. "
                "Tôi sẽ áp 'no shutdown' để khôi phục.",
                tool_calls=[("push_config", {"node_id": "R2", "config_lines": ["interface Gi0/1", "no shutdown"]})],
            )
        ]
    )
    recorder = InMemoryIncidentRecorder()
    engine = SelfHealingEngine(llm=llm, tool_runner=tool_runner, recorder=recorder, max_retries=3)

    incident = IncidentView(id="demo-kb01", description="R1 mất kết nối tới R2", device_ids=["R1", "R2"])

    outcome = engine.tu_khac_phuc(incident)

    print("--- Nhật ký hành động (action_logs) ---")
    for incident_id, tool, arguments, result in recorder.actions:
        print(f"  [{tool}] tham số={arguments} -> kết quả={result}")

    print("\n--- Diễn biến trạng thái sự cố ---")
    for _, status in recorder.events:
        print(f"  -> {status}")

    print(f"\nKết quả cuối cùng : {outcome.status} ({outcome.detail})")
    print(f"Trạng thái R2/Gi0/1: {devices['R2'].interfaces['Gi0/1'].status}")
    assert outcome.status == "resolved" and devices["R2"].interfaces["Gi0/1"].status == "up"
    print("\n✓ Vòng lặp Observe-Think-Act-Verify hoạt động đúng: agent tự chẩn đoán, tự sửa và tự kiểm chứng.")


def demo_high_risk_approval() -> None:
    _print_header("KỊCH BẢN KB08 (Bảng 5.2): quét cổng -> đề xuất chặn IP (cần phê duyệt)")

    devices = {"R1": FakeDevice(id="R1")}
    tool_runner = FakeToolRunner(devices)
    recorder = InMemoryIncidentRecorder()
    plan_call = [("block_ip", {"node_id": "R1", "ip_address": "203.0.113.9"})]

    llm1 = FakeLLMClient([ScriptedStep(content="Phát hiện quét cổng từ 203.0.113.9, đề xuất chặn tại R1.", tool_calls=plan_call)])
    engine1 = SelfHealingEngine(llm=llm1, tool_runner=tool_runner, recorder=recorder, max_retries=3)
    incident = IncidentView(id="demo-kb08", description="Quét cổng từ 203.0.113.9", device_ids=["R1"])

    outcome1 = engine1.tu_khac_phuc(incident)
    print(f"Lượt 1 (chưa phê duyệt): {outcome1.status} - guardrail chặn thực thi block_ip (hành động rủi ro cao).")
    assert outcome1.status == "awaiting_approval"
    assert recorder.actions == []

    approved_incident = IncidentView(
        id="demo-kb08",
        description="Quét cổng từ 203.0.113.9",
        device_ids=["R1"],
        pending_action={**recorder.pending_action["demo-kb08"], "approved": True},
    )
    llm2 = FakeLLMClient([ScriptedStep(content="Phát hiện quét cổng từ 203.0.113.9, đề xuất chặn tại R1.", tool_calls=plan_call)])
    engine2 = SelfHealingEngine(llm=llm2, tool_runner=tool_runner, recorder=recorder, max_retries=3)
    outcome2 = engine2.tu_khac_phuc(approved_incident)

    print(f"Lượt 2 (đã phê duyệt): {outcome2.status} - đã thực thi {recorder.actions[-1][1]}.")
    assert outcome2.status == "resolved"
    print("\n✓ Guardrail hoạt động đúng: hành động rủi ro cao bị giữ lại chờ con người, chỉ chạy sau khi được duyệt.")


def demo_copilot() -> None:
    _print_header("COPILOT: hỏi đáp và đề xuất hành động cần xác nhận")

    devices = {"R2": FakeDevice(id="R2", interfaces={"Gi0/1": FakeInterface(name="Gi0/1", status="down")})}
    tool_runner = FakeToolRunner(devices)

    llm = FakeLLMClient(
        [
            ScriptedStep(content="Để tôi kiểm tra trạng thái cổng trên R2.", tool_calls=[("get_interfaces", {"node_id": "R2"})]),
            ScriptedStep(content="Trên R2, cổng Gi0/1 đang down - đây là nguyên nhân R1 không kết nối được. "
            "Bạn có muốn tôi bật lại cổng này không?"),
        ]
    )
    engine = CopilotEngine(llm=llm, tool_runner=tool_runner)

    question = "Vì sao R1 không kết nối được tới R2?"
    print(f'Kỹ sư hỏi: "{question}"')
    messages = [{"role": "system", "content": COPILOT_SYSTEM_PROMPT}, {"role": "user", "content": question}]
    turn = engine.ask(messages)
    print(f"Copilot  : {turn.text}")
    print(f"  (đã tự gọi {len(turn.tool_calls)} tool chỉ đọc: {[t['name'] for t in turn.tool_calls]})")

    _print_header("COPILOT: đề xuất hành động thay đổi cấu hình - cần xác nhận")
    llm2 = FakeLLMClient(
        [ScriptedStep(content="", tool_calls=[("push_config", {"node_id": "R2", "config_lines": ["interface Gi0/1", "no shutdown"]})])]
    )
    engine2 = CopilotEngine(llm=llm2, tool_runner=tool_runner)
    request = "Bật lại cổng Gi0/1 trên R2 giúp tôi."
    print(f'Kỹ sư yêu cầu: "{request}"')
    turn2 = engine2.ask([{"role": "system", "content": COPILOT_SYSTEM_PROMPT}, {"role": "user", "content": request}])
    print(f"Copilot      : {turn2.text}")
    print(f"  requires_confirmation={turn2.requires_confirmation}, pending_action={turn2.pending_action}")
    assert turn2.requires_confirmation is True
    assert devices["R2"].interfaces["Gi0/1"].status == "down"  # chưa xác nhận thì chưa thực thi

    print('\nKỹ sư xác nhận: "có, thực hiện đi"')
    turn3 = engine2.confirm(turn2.pending_action)
    print(f"Copilot        : {turn3.text}")
    assert devices["R2"].interfaces["Gi0/1"].status == "up"
    print("\n✓ Copilot tách bạch đúng đọc (tự do) và ghi (cần xác nhận) trước khi thực thi.")


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    if target in ("self-healing", "all"):
        demo_self_healing()
        demo_high_risk_approval()
    if target in ("copilot", "all"):
        demo_copilot()
    print(f"\n{RULE}\nHoàn tất demo lõi AI Agent (app.agent_core) - không cần API key/DB/GNS3.\n{RULE}")


if __name__ == "__main__":
    sys.exit(main())
