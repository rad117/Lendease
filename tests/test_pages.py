"""Open every page once with canned rows, to catch template mistakes."""
from datetime import date, datetime
from decimal import Decimal

import pymysql

import app as lendease
from tests.conftest import login_session
from tests.test_app import PRODUCT


def test_home_shows_rates_and_banks(client, fake_db):
    # The fake returns the same rows for every query, so one row carries both shapes.
    fake_db.query_result = [{"bank_id": 1, "name": "State Bank of India", "short_name": "SBI",
                             "loan_type": "Home Loan", "from_rate": Decimal("8.45"), "bank_count": 6}]
    res = client.get("/")
    assert res.status_code == 200
    assert b"Covering SBI" in res.data and b"from 8.45%" in res.data
    assert b"not a lender" in res.data


def test_emi_calculator_page(client):
    assert client.get("/emi-calculator").status_code == 200


def test_compare_page_lists_banks(client, fake_db):
    fake_db.query_result = [{"bank_id": 1, "name": "HDFC Bank", "short_name": "HDFC"}]
    assert b"HDFC Bank" in client.get("/loans/compare").data


def test_detail_shows_source_and_last_updated(client, fake_db):
    fake_db.one_result = PRODUCT
    res = client.get("/loans/1")
    assert res.status_code == 200
    assert b"https://sbi.co.in" in res.data and b"30 Sep 2026" in res.data
    assert "₹5,00,000".encode() in res.data


def test_detail_404_for_unknown_product(client, fake_db):
    fake_db.one_result = None
    assert client.get("/loans/999").status_code == 404


def test_dashboard_needs_login(client):
    res = client.get("/dashboard")
    assert res.status_code == 302 and "/auth/login" in res.headers["Location"]


def test_dashboard_shows_saved_offers_and_history(client, fake_db):
    login_session(client)
    fake_db.query_result = [dict(PRODUCT, saved_id=1, saved_at=datetime(2026, 10, 1), history_id=4,
                                 amount=Decimal("3000000.00"), tenure_months=240,
                                 searched_at=datetime(2026, 10, 2, 9, 30), best_rate_now=Decimal("8.50"))]
    res = client.get("/dashboard")
    assert res.status_code == 200 and b"SBI Home Loan" in res.data
    assert "₹30,00,000".encode() in res.data and b"20 yrs" in res.data


def test_admin_pages_open(client, fake_db):
    login_session(client, is_admin=True)
    fake_db.one_result = dict(PRODUCT, users=2, banks=6, products=30, saved=2, name="State Bank of India")
    fake_db.query_result = [dict(PRODUCT, name="State Bank of India", product_count=5, is_active=1,
                                 recorded_at=datetime(2026, 9, 30), change_note="x", changed_by="Admin")]
    for path in ("/admin", "/admin/banks", "/admin/products", "/admin/banks/new", "/admin/products/new",
                 "/admin/products/1/edit", "/admin/banks/1/edit"):
        assert client.get(path).status_code == 200, path


def test_unknown_url_shows_error_page(client):
    res = client.get("/nope")
    assert res.status_code == 404 and b"Page not found" in res.data


def test_database_down_shows_friendly_error(client, monkeypatch):
    def down(*args, **kwargs):
        raise pymysql.err.OperationalError(2003, "can't connect")

    monkeypatch.setattr(lendease, "query", down)
    res = client.get("/loans/compare")
    assert res.status_code == 503 and b"Database unavailable" in res.data
    api = client.get("/api/compare?loan_type=Home%20Loan")
    assert api.status_code == 503 and "database" in api.get_json()["error"].lower()
