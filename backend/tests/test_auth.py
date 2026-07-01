def test_register_and_login(client) -> None:
    response = client.post(
        "/api/auth/register", json={"username": "engineer1", "password": "secret123", "role": "engineer"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "engineer1"

    login_response = client.post(
        "/api/auth/login", data={"username": "engineer1", "password": "secret123"}
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    assert token


def test_login_with_wrong_password_fails(client) -> None:
    client.post("/api/auth/register", json={"username": "engineer2", "password": "secret123"})
    response = client.post("/api/auth/login", data={"username": "engineer2", "password": "wrong"})
    assert response.status_code == 401


def test_approve_incident_requires_auth(client) -> None:
    response = client.post("/api/incidents/does-not-exist/approve", json={"approved": True})
    assert response.status_code == 401
