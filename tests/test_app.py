"""API, login and admin access rules."""
from datetime import date
from decimal import Decimal

from werkzeug.security import generate_password_hash

from tests.conftest import CSRF, login_session

PRODUCT = {
    "product_id": 1, "product_name": "SBI Home Loan", "loan_type": "Home Loan",
    "min_interest_rate": Decimal("8.50"), "max_interest_rate": Decimal("9.65"),
    "min_amount": Decimal("500000.00"), "max_amount": Decimal("100000000.00"),
    "min_tenure_months": 60, "max_tenure_months": 360,
    "processing_fee_percent": Decimal("0.35"), "processing_fee_flat": Decimal("0.00"),
    "eligibility_criteria": None, "source_url": "https://sbi.co.in",
    "last_updated": date(2026, 9, 30), "bank_id": 1, "bank_name": "State Bank of India",
    "short_name": "SBI", "website_url": None,
}


def test_compare_rejects_unknown_loan_type(client):
    assert client.get("/api/compare?loan_type=Yacht%20Loan").status_code == 400


def test_compare_rejects_bad_number(client):
    res = client.get("/api/compare?loan_type=Home%20Loan&amount=abc")
    assert res.status_code == 400 and "amount" in res.get_json()["error"]


def test_compare_sends_filters_as_parameters_not_sql_text(client, fake_db):
    fake_db.query_result = [PRODUCT]
    res = client.get("/api/compare?loan_type=Home%20Loan&amount=3000000&tenure=240&bank_id=1")
    body = res.get_json()

    assert res.status_code == 200 and body["count"] == 1
    assert body["results"][0]["min_interest_rate"] == 8.5        # Decimal -> number
    assert body["results"][0]["last_updated"] == "2026-09-30"    # date -> text

    sql, params = fake_db.queries[0]
    assert "3000000" not in sql and "Home Loan" not in sql        # values never glued into the SQL
    assert params == ["Home Loan", 3000000.0, 3000000.0, 240, 240, 1]
    assert fake_db.executed == []                                  # a logged-out search isn't recorded


def test_compare_records_history_for_logged_in_user(client, fake_db):
    login_session(client, user_id=7)
    client.get("/api/compare?loan_type=Home%20Loan&amount=3000000&tenure=240")
    assert any("INSERT INTO comparison_history" in sql and params[0] == 7 for sql, params in fake_db.executed)


def test_save_offer_needs_login(client):
    with client.session_transaction() as s:
        s["csrf_token"] = "tok"
    assert client.post("/api/save-offer", json={"product_id": 1}, headers=CSRF).status_code == 401


def test_save_offer_inserts_for_current_user(client, fake_db):
    login_session(client, user_id=7)
    fake_db.one_result = {"product_id": 3}
    res = client.post("/api/save-offer", json={"product_id": 3}, headers=CSRF)
    assert res.status_code == 201 and fake_db.executed[-1][1] == [7, 3]


def test_post_without_csrf_token_is_rejected(client):
    assert client.post("/auth/login", data={"email": "a@b.co", "password": "x"}).status_code == 400


def test_login_sets_session_and_ignores_outside_redirects(client, fake_db):
    fake_db.one_result = {"user_id": 9, "full_name": "Demo", "is_admin": 0,
                          "password_hash": generate_password_hash("Demo@123")}
    login_session(client)
    res = client.post("/auth/login", data={"email": "demo@lendease.com", "password": "Demo@123",
                                           "csrf_token": "tok", "next": "//evil.example"})
    assert res.status_code == 302 and "evil.example" not in res.headers["Location"]
    with client.session_transaction() as s:
        assert s["user_id"] == 9


def test_login_wrong_password(client, fake_db):
    fake_db.one_result = {"user_id": 9, "full_name": "Demo", "is_admin": 0,
                          "password_hash": generate_password_hash("Demo@123")}
    login_session(client)
    res = client.post("/auth/login", data={"email": "demo@lendease.com", "password": "nope", "csrf_token": "tok"})
    assert res.status_code == 401


def test_register_checks_password_length(client):
    login_session(client)
    res = client.post("/auth/register", data={"full_name": "A", "email": "a@b.co", "password": "short",
                                              "confirm_password": "short", "csrf_token": "tok"})
    assert res.status_code == 400


def test_admin_blocked_for_normal_user_and_redirects_when_logged_out(client):
    res = client.get("/admin")
    assert res.status_code == 302 and "/auth/login" in res.headers["Location"]
    login_session(client, is_admin=False)
    assert client.get("/admin").status_code == 403
    assert client.get("/admin/products").status_code == 403


def test_admin_product_rejects_min_above_max(client, fake_db):
    login_session(client, is_admin=True)
    form = {"csrf_token": "tok", "bank_id": "1", "loan_type": "Home Loan", "product_name": "X",
            "min_interest_rate": "9", "max_interest_rate": "8", "min_amount": "1000", "max_amount": "5000",
            "min_tenure_months": "12", "max_tenure_months": "24", "processing_fee_percent": "0.5",
            "processing_fee_flat": "0", "source_url": "https://example.com"}
    assert client.post("/admin/products/new", data=form).status_code == 400
    assert fake_db.executed == []
