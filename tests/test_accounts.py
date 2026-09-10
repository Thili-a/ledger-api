from tests.conftest import auth_headers, register_and_login


def open_account(client, token, currency="EUR", opening_balance_minor=0):
    response = client.post(
        "/accounts",
        json={"currency": currency, "opening_balance_minor": opening_balance_minor},
        headers=auth_headers(token),
    )
    assert response.status_code == 201
    return response.json()


def test_customer_can_open_and_view_own_account(client):
    token = register_and_login(client, "dave@example.com")
    account = open_account(client, token, opening_balance_minor=5000)
    assert account["balance_minor"] == 5000

    response = client.get(f"/accounts/{account['id']}", headers=auth_headers(token))
    assert response.status_code == 200


def test_customer_cannot_view_others_account(client):
    token_a = register_and_login(client, "eve@example.com")
    token_b = register_and_login(client, "frank@example.com")
    account = open_account(client, token_a)

    response = client.get(f"/accounts/{account['id']}", headers=auth_headers(token_b))
    assert response.status_code == 403


def test_customer_cannot_search_accounts(client):
    token = register_and_login(client, "grace@example.com")
    response = client.get("/accounts", headers=auth_headers(token))
    assert response.status_code == 403


def test_support_can_search_and_freeze_account(client):
    customer_token = register_and_login(client, "heidi@example.com")
    support_token = register_and_login(client, "support1@example.com", role="support")
    account = open_account(client, customer_token)

    search = client.get("/accounts?q=heidi", headers=auth_headers(support_token))
    assert search.status_code == 200
    assert any(a["id"] == account["id"] for a in search.json())

    freeze = client.post(f"/accounts/{account['id']}/freeze", headers=auth_headers(support_token))
    assert freeze.status_code == 200
    assert freeze.json()["is_frozen"] is True

    unfreeze = client.post(f"/accounts/{account['id']}/unfreeze", headers=auth_headers(support_token))
    assert unfreeze.json()["is_frozen"] is False
