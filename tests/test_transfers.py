from tests.conftest import auth_headers, register_and_login


def open_account(client, token, opening_balance_minor=0):
    response = client.post(
        "/accounts",
        json={"currency": "EUR", "opening_balance_minor": opening_balance_minor},
        headers=auth_headers(token),
    )
    return response.json()


def transfer(client, token, from_id, to_id, amount, idempotency_key="key-1"):
    return client.post(
        "/transfers",
        json={"from_account_id": from_id, "to_account_id": to_id, "amount_minor": amount, "currency": "EUR"},
        headers={**auth_headers(token), "Idempotency-Key": idempotency_key},
    )


def test_successful_transfer_moves_balances(client):
    token = register_and_login(client, "ivan@example.com")
    a = open_account(client, token, opening_balance_minor=10000)
    b = open_account(client, token, opening_balance_minor=0)

    response = transfer(client, token, a["id"], b["id"], 2500)
    assert response.status_code == 201
    assert response.json()["status"] == "completed"

    assert client.get(f"/accounts/{a['id']}", headers=auth_headers(token)).json()["balance_minor"] == 7500
    assert client.get(f"/accounts/{b['id']}", headers=auth_headers(token)).json()["balance_minor"] == 2500


def test_idempotency_key_prevents_double_transfer(client):
    token = register_and_login(client, "judy@example.com")
    a = open_account(client, token, opening_balance_minor=10000)
    b = open_account(client, token, opening_balance_minor=0)

    first = transfer(client, token, a["id"], b["id"], 2500, idempotency_key="same-key")
    second = transfer(client, token, a["id"], b["id"], 2500, idempotency_key="same-key")

    assert first.json()["id"] == second.json()["id"]
    assert client.get(f"/accounts/{a['id']}", headers=auth_headers(token)).json()["balance_minor"] == 7500


def test_insufficient_funds_rejected_and_recorded(client):
    token = register_and_login(client, "mallory@example.com")
    a = open_account(client, token, opening_balance_minor=100)
    b = open_account(client, token, opening_balance_minor=0)

    response = transfer(client, token, a["id"], b["id"], 5000)
    assert response.status_code == 402
    assert client.get(f"/accounts/{a['id']}", headers=auth_headers(token)).json()["balance_minor"] == 100


def test_transfer_from_frozen_account_rejected(client):
    customer_token = register_and_login(client, "niaj@example.com")
    support_token = register_and_login(client, "support2@example.com", role="support")
    a = open_account(client, customer_token, opening_balance_minor=10000)
    b = open_account(client, customer_token, opening_balance_minor=0)

    client.post(f"/accounts/{a['id']}/freeze", headers=auth_headers(support_token))
    response = transfer(client, customer_token, a["id"], b["id"], 1000)
    assert response.status_code == 409


def test_large_transfer_requires_approval(client):
    customer_token = register_and_login(client, "olivia@example.com")
    support_token = register_and_login(client, "support3@example.com", role="support")
    a = open_account(client, customer_token, opening_balance_minor=1_000_000)
    b = open_account(client, customer_token, opening_balance_minor=0)

    response = transfer(client, customer_token, a["id"], b["id"], 150_000)
    assert response.status_code == 201
    assert response.json()["status"] == "pending_approval"
    assert client.get(f"/accounts/{a['id']}", headers=auth_headers(customer_token)).json()["balance_minor"] == 1_000_000

    pending = client.get("/transfers/pending", headers=auth_headers(support_token))
    assert len(pending.json()) == 1

    transaction_id = response.json()["id"]
    approve = client.post(f"/transfers/{transaction_id}/approve", headers=auth_headers(support_token))
    assert approve.status_code == 200
    assert approve.json()["status"] == "completed"
    assert client.get(f"/accounts/{a['id']}", headers=auth_headers(customer_token)).json()["balance_minor"] == 850_000


def test_customer_cannot_approve_transfers(client):
    customer_token = register_and_login(client, "peggy@example.com")
    a = open_account(client, customer_token, opening_balance_minor=1_000_000)
    b = open_account(client, customer_token, opening_balance_minor=0)
    response = transfer(client, customer_token, a["id"], b["id"], 150_000)
    transaction_id = response.json()["id"]

    approve = client.post(f"/transfers/{transaction_id}/approve", headers=auth_headers(customer_token))
    assert approve.status_code == 403


def test_completed_transfer_publishes_event(client, publisher):
    token = register_and_login(client, "quentin@example.com")
    a = open_account(client, token, opening_balance_minor=10000)
    b = open_account(client, token, opening_balance_minor=0)

    response = transfer(client, token, a["id"], b["id"], 2500)
    assert publisher.published == [response.json()["id"]]
