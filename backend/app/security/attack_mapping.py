"""Ánh xạ dấu hiệu tấn công sang khung MITRE ATT&CK - mục 2.7, 3.3.4."""

from __future__ import annotations

ATTACK_MAPPING: dict[str, dict[str, str]] = {
    "port_scan": {"technique_id": "T1046", "technique_name": "Network Service Discovery", "tactic": "Discovery"},
    "syn_flood": {"technique_id": "T1499", "technique_name": "Endpoint Denial of Service", "tactic": "Impact"},
    "dos": {"technique_id": "T1499", "technique_name": "Endpoint Denial of Service", "tactic": "Impact"},
    "ssh_bruteforce": {"technique_id": "T1110", "technique_name": "Brute Force", "tactic": "Credential Access"},
    "password_guessing": {
        "technique_id": "T1110.001",
        "technique_name": "Password Guessing",
        "tactic": "Credential Access",
    },
    "mirai_botnet": {
        "technique_id": "T1584.008",
        "technique_name": "Compromise Infrastructure: Network Devices",
        "tactic": "Resource Development",
    },
    "rpl_attack": {
        "technique_id": "T0836",
        "technique_name": "Denial of Control (Routing Protocol Attack)",
        "tactic": "Impact",
    },
}


def map_indicators(indicators: list[str]) -> list[dict]:
    """Ánh xạ tập dấu hiệu (Bảng 3.3: map_attack) sang kỹ thuật/chiến thuật ATT&CK."""
    mapped = []
    for indicator in indicators:
        entry = ATTACK_MAPPING.get(indicator)
        if entry:
            mapped.append({"indicator": indicator, **entry})
        else:
            mapped.append(
                {"indicator": indicator, "technique_id": "unknown", "technique_name": "unknown", "tactic": "unknown"}
            )
    return mapped
