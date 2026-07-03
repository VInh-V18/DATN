from app.core.agent_trace import record_trace
from app.models.models import TraceSubjectType


def test_list_agent_traces_endpoint(client) -> None:
    from app.core.database import get_db
    from app.main import app

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        record_trace(db, TraceSubjectType.incident, "inc-1", "get_interfaces", {"node_id": "R2"}, {"status": "down"}, True)
        record_trace(db, TraceSubjectType.security_alert, "alert-1", "block_ip", {"node_id": "R1"}, {"ok": True}, False)
    finally:
        db.close()

    response = client.get("/api/agent-traces")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {row["tool"] for row in body} == {"get_interfaces", "block_ip"}

    response = client.get("/api/agent-traces", params={"subject_type": "incident", "subject_id": "inc-1"})
    assert response.status_code == 200
    filtered = response.json()
    assert len(filtered) == 1
    assert filtered[0]["subject_id"] == "inc-1"
    assert filtered[0]["read_only"] is True
