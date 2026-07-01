"""Đánh giá định lượng hệ thống - Bảng 5.3, mục 5.3 và GĐ6 (Bảng 5.4).

Tính toán các chỉ số từ dữ liệu đã ghi nhận trong DB (incidents, action_logs,
security_alerts, chat_messages) sau khi chạy các kịch bản fault injection
(scripts/fault_injection.py). Một số chỉ số cần nhãn thực tế (ground truth)
không có sẵn trong hệ thống - ví dụ độ chính xác chẩn đoán nguyên nhân gốc,
F1 phát hiện bất thường, recall phát hiện tấn công - có thể cung cấp qua
`--labels labels.json` (xem cấu trúc mẫu trong `--help`); nếu không cung cấp,
báo cáo sẽ bỏ qua các chỉ số đó và ghi rõ lý do.

Sử dụng:
    python -m scripts.evaluate
    python -m scripts.evaluate --labels eval_labels.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.models import ActionLog, ChatMessage, ChatSession, Incident, IncidentStatus, SecurityAlert

LABELS_EXAMPLE = {
    "root_cause_labels": {"<incident_id>": "expected keyword trong root_cause, ví dụ 'shutdown'"},
    "injected_attacks": [
        {"scenario": "KB08", "source_ip": "192.168.1.100", "injected_at": "2026-07-01T10:00:00"}
    ],
}


@dataclass
class EvaluationReport:
    total_incidents: int = 0
    resolved_incidents: int = 0
    self_healing_rate: float | None = None
    mttr_seconds: float | None = None
    diagnosis_accuracy: float | None = None
    copilot_avg_response_seconds: float | None = None
    security_alerts_total: int = 0
    security_response_accuracy: float | None = None
    attack_detection_recall: float | None = None
    failed_actions_count: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "tỉ_lệ_tự_khắc_phục": self.self_healing_rate,
            "mttr_giây": self.mttr_seconds,
            "độ_chính_xác_chẩn_đoán": self.diagnosis_accuracy,
            "thời_gian_phản_hồi_copilot_giây": self.copilot_avg_response_seconds,
            "tỉ_lệ_phản_ứng_an_ninh_đúng": self.security_response_accuracy,
            "recall_phát_hiện_tấn_công": self.attack_detection_recall,
            "hành_động_thất_bại": self.failed_actions_count,
            "tổng_số_sự_cố": self.total_incidents,
            "tổng_số_cảnh_báo_an_ninh": self.security_alerts_total,
            "ghi_chú": self.notes,
        }


def evaluate_self_healing(db, report: EvaluationReport) -> None:
    incidents = db.execute(select(Incident)).scalars().all()
    report.total_incidents = len(incidents)
    resolved = [i for i in incidents if i.status == IncidentStatus.resolved]
    report.resolved_incidents = len(resolved)
    if incidents:
        report.self_healing_rate = len(resolved) / len(incidents)

    durations = [
        (i.resolved_at - i.timestamp).total_seconds() for i in resolved if i.resolved_at is not None
    ]
    if durations:
        report.mttr_seconds = sum(durations) / len(durations)


def evaluate_diagnosis_accuracy(db, report: EvaluationReport, root_cause_labels: dict[str, str]) -> None:
    if not root_cause_labels:
        report.notes.append("Bỏ qua 'độ chính xác chẩn đoán': chưa cung cấp root_cause_labels trong --labels.")
        return
    correct = 0
    for incident_id, expected_keyword in root_cause_labels.items():
        incident = db.get(Incident, incident_id)
        if incident and incident.root_cause and expected_keyword.lower() in incident.root_cause.lower():
            correct += 1
    report.diagnosis_accuracy = correct / len(root_cause_labels)


def evaluate_copilot_response_time(db, report: EvaluationReport) -> None:
    sessions = db.execute(select(ChatSession)).scalars().all()
    deltas: list[float] = []
    for session in sessions:
        messages = sorted(session.messages, key=lambda m: m.timestamp)
        for prev, curr in zip(messages, messages[1:]):
            if prev.role == "user" and curr.role == "assistant":
                deltas.append((curr.timestamp - prev.timestamp).total_seconds())
    if deltas:
        report.copilot_avg_response_seconds = sum(deltas) / len(deltas)
    else:
        report.notes.append("Chưa có lượt hội thoại nào để tính thời gian phản hồi Copilot.")


def evaluate_security_response(db, report: EvaluationReport) -> None:
    alerts = db.execute(select(SecurityAlert)).scalars().all()
    report.security_alerts_total = len(alerts)
    actionable = [a for a in alerts if a.status != "alert_only"]
    correct = [a for a in actionable if a.status == "blocked"]
    if actionable:
        report.security_response_accuracy = len(correct) / len(actionable)
    else:
        report.notes.append("Chưa có cảnh báo an ninh nào yêu cầu phản ứng để tính tỉ lệ phản ứng đúng.")


def evaluate_attack_recall(db, report: EvaluationReport, injected_attacks: list[dict]) -> None:
    if not injected_attacks:
        report.notes.append("Bỏ qua 'recall phát hiện tấn công': chưa cung cấp injected_attacks trong --labels.")
        return
    detected = 0
    for attack in injected_attacks:
        source_ip = attack["source_ip"]
        injected_at = datetime.fromisoformat(attack["injected_at"])
        match = (
            db.query(SecurityAlert)
            .filter(SecurityAlert.source_ip == source_ip, SecurityAlert.timestamp >= injected_at)
            .first()
        )
        if match is not None:
            detected += 1
    report.attack_detection_recall = detected / len(injected_attacks)


def evaluate_failed_actions(db, report: EvaluationReport) -> None:
    logs = db.execute(select(ActionLog)).scalars().all()
    report.failed_actions_count = sum(1 for log in logs if isinstance(log.result, dict) and "error" in log.result)
    report.notes.append(
        "'Hành động thất bại' chỉ đếm số lần tool trả lỗi (proxy) - đánh giá 'gây hại thực sự' "
        "theo NFR mục 3.1 cần kiểm tra thủ công thêm."
    )


def run_evaluation(labels: dict) -> EvaluationReport:
    report = EvaluationReport()
    db = SessionLocal()
    try:
        evaluate_self_healing(db, report)
        evaluate_diagnosis_accuracy(db, report, labels.get("root_cause_labels", {}))
        evaluate_copilot_response_time(db, report)
        evaluate_security_response(db, report)
        evaluate_attack_recall(db, report, labels.get("injected_attacks", []))
        evaluate_failed_actions(db, report)
    finally:
        db.close()
    return report


def print_report(report: EvaluationReport) -> None:
    def fmt(value, suffix="") -> str:
        return "—" if value is None else f"{value:.3f}{suffix}"

    print("=== Báo cáo đánh giá định lượng (Bảng 5.3) ===")
    print(f"Tỉ lệ tự khắc phục       : {fmt(report.self_healing_rate)} (mục tiêu ≥ 0.80)")
    print(f"MTTR (agent)             : {fmt(report.mttr_seconds, ' giây')}")
    print(f"Độ chính xác chẩn đoán   : {fmt(report.diagnosis_accuracy)} (mục tiêu ≥ 0.85)")
    print(f"Thời gian phản hồi Copilot: {fmt(report.copilot_avg_response_seconds, ' giây')} (mục tiêu < 10s)")
    print(f"Tỉ lệ phản ứng an ninh đúng: {fmt(report.security_response_accuracy)} (mục tiêu ≥ 0.90)")
    print(f"Recall phát hiện tấn công : {fmt(report.attack_detection_recall)} (mục tiêu ≥ 0.90)")
    print(f"Hành động thất bại (proxy): {report.failed_actions_count} (mục tiêu = 0)")
    print(f"Tổng số sự cố            : {report.total_incidents} (đã giải quyết: {report.resolved_incidents})")
    print(f"Tổng số cảnh báo an ninh : {report.security_alerts_total}")
    if report.notes:
        print("\nGhi chú:")
        for note in report.notes:
            print(f"  - {note}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Cấu trúc file --labels mẫu:\n{json.dumps(LABELS_EXAMPLE, ensure_ascii=False, indent=2)}",
    )
    parser.add_argument("--labels", help="Đường dẫn file JSON chứa nhãn thực tế (xem --help)")
    parser.add_argument("--json", action="store_true", help="In kết quả dạng JSON thay vì báo cáo dạng văn bản")
    args = parser.parse_args()

    labels = {}
    if args.labels:
        with open(args.labels, encoding="utf-8") as f:
            labels = json.load(f)

    report = run_evaluation(labels)
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, default=str))
    else:
        print_report(report)


if __name__ == "__main__":
    sys.exit(main())
