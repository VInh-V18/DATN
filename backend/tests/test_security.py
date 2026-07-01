from datetime import datetime, timedelta

from app.security.attack_mapping import map_indicators
from app.security.detection import SecurityDetectionEngine


def test_map_indicators_known() -> None:
    mapped = map_indicators(["port_scan", "ssh_bruteforce"])
    assert mapped[0]["technique_id"] == "T1046"
    assert mapped[1]["technique_id"] == "T1110"


def test_map_indicators_unknown() -> None:
    mapped = map_indicators(["something_else"])
    assert mapped[0]["technique_id"] == "unknown"


def test_port_scan_detection_triggers_after_threshold() -> None:
    engine = SecurityDetectionEngine()
    now = datetime.utcnow()
    result = None
    for port in range(1, 20):
        result = engine.ingest_flow("10.0.0.5", port, timestamp=now + timedelta(milliseconds=port))
    assert result is not None
    assert result.indicator == "port_scan"
    assert result.source_ip == "10.0.0.5"


def test_ssh_bruteforce_detection() -> None:
    engine = SecurityDetectionEngine()
    now = datetime.utcnow()
    result = None
    for i in range(6):
        result = engine.ingest_failed_login("10.0.0.9", timestamp=now + timedelta(seconds=i))
    assert result is not None
    assert result.indicator == "ssh_bruteforce"
