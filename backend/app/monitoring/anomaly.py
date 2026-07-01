"""Phát hiện bất thường bằng Isolation Forest - mục 2.6, 3.3.1.

Vec-tơ đặc trưng cho mỗi thiết bị gồm: CPU/RAM, lưu lượng vào/ra, tỉ lệ rớt gói
và số gói lỗi, số lần thay đổi trạng thái cổng, số lượng/tần suất bản tin syslog.
Isolation Forest được chọn vì không cần dữ liệu gán nhãn và nhẹ về tính toán.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import IsolationForest

from app.core.config import get_settings

FEATURE_NAMES = [
    "cpu_percent",
    "memory_percent",
    "bandwidth_in_mbps",
    "bandwidth_out_mbps",
    "packet_loss_rate",
    "interface_errors",
    "port_flap_count",
    "syslog_rate",
]


@dataclass
class AnomalyScore:
    is_anomaly: bool
    score: float
    features: dict[str, float] = field(default_factory=dict)


class AnomalyDetector:
    """Bọc scikit-learn IsolationForest; huấn luyện trên dữ liệu lịch sử của từng thiết bị."""

    def __init__(self, contamination: float = 0.05, random_state: int = 42) -> None:
        self.model = IsolationForest(contamination=contamination, random_state=random_state)
        self._fitted = False
        self._threshold = get_settings().anomaly_score_threshold

    def fit(self, historical_series: list[list[float]]) -> None:
        if len(historical_series) < 10:
            return
        self.model.fit(np.array(historical_series))
        self._fitted = True

    def score(self, series: list[list[float]]) -> dict:
        """Dùng cho tool detect_anomaly(): huấn luyện nhanh trên chuỗi truyền vào rồi
        chấm điểm điểm dữ liệu cuối cùng so với phần còn lại của chuỗi."""
        if len(series) < 2:
            return {"is_anomaly": False, "score": 0.0}
        data = np.array(series)
        model = IsolationForest(contamination=0.1, random_state=42)
        model.fit(data)
        scores = model.decision_function(data)
        predictions = model.predict(data)
        last_score = float(scores[-1])
        last_is_anomaly = bool(predictions[-1] == -1)
        return {"is_anomaly": last_is_anomaly, "score": last_score, "all_scores": scores.tolist()}

    def score_single(self, feature_vector: list[float]) -> AnomalyScore:
        if not self._fitted:
            return AnomalyScore(is_anomaly=False, score=0.0, features=dict(zip(FEATURE_NAMES, feature_vector)))
        arr = np.array([feature_vector])
        score = float(self.model.decision_function(arr)[0])
        return AnomalyScore(
            is_anomaly=score < self._threshold,
            score=score,
            features=dict(zip(FEATURE_NAMES, feature_vector)),
        )


def build_feature_vector(
    cpu_percent: float = 0.0,
    memory_percent: float = 0.0,
    bandwidth_in_mbps: float = 0.0,
    bandwidth_out_mbps: float = 0.0,
    packet_loss_rate: float = 0.0,
    interface_errors: float = 0.0,
    port_flap_count: float = 0.0,
    syslog_rate: float = 0.0,
) -> list[float]:
    return [
        cpu_percent,
        memory_percent,
        bandwidth_in_mbps,
        bandwidth_out_mbps,
        packet_loss_rate,
        interface_errors,
        port_flap_count,
        syslog_rate,
    ]
