def test_register_and_login(client):
    response = client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "password123", "full_name": "Alice"},
    )
    assert response.status_code == 201
    assert response.json()["email"] == "alice@example.com"

    response = client.post(
        "/auth/login", data={"username": "alice@example.com", "password": "password123"}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_wrong_password_rejected(client):
    client.post(
        "/auth/register",
        json={"email": "bob@example.com", "password": "password123", "full_name": "Bob"},
    )
    response = client.post("/auth/login", data={"username": "bob@example.com", "password": "wrong"})
    assert response.status_code == 401


def test_duplicate_registration_rejected(client):
    payload = {"email": "carol@example.com", "password": "password123", "full_name": "Carol"}
    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/register", json=payload).status_code == 409


def test_protected_endpoint_requires_token(client):
    response = client.get("/accounts")
    assert response.status_code == 401
