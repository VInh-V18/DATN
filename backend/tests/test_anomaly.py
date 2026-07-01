import numpy as np

from app.monitoring.anomaly import AnomalyDetector, build_feature_vector


def test_build_feature_vector_order() -> None:
    vec = build_feature_vector(cpu_percent=50, memory_percent=30)
    assert vec[0] == 50
    assert vec[1] == 30
    assert len(vec) == 8


def test_detect_anomaly_flags_outlier() -> None:
    detector = AnomalyDetector()
    rng = np.random.default_rng(0)
    normal = [[float(x)] for x in rng.normal(loc=10, scale=1, size=30)]
    series = normal + [[500.0]]
    result = detector.score(series)
    assert result["is_anomaly"] is True
