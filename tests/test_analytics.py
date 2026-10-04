import csv
import io
from datetime import date, datetime
from decimal import Decimal


def test_analytics_page_has_filters_and_chart_areas(client):
    res = client.get("/analytics")
    assert res.status_code == 200
    charts = ("chart-rates", "chart-emi", "chart-split", "chart-emi-tenure", "chart-interest-tenure",
              "chart-fee", "chart-by-type", "chart-by-bank", "chart-searches", "chart-saved")
    for chart_id in charts:
        assert f'<canvas id="{chart_id}"'.encode() in res.data, chart_id
    assert b'id="analytics-form"' in res.data and b"/analytics/export/loan_products.csv" in res.data
    assert b"chart.umd.min.js" in res.data          # Chart.js is loaded on this page
    assert b"ableau" not in res.data


def test_chart_library_is_only_loaded_on_the_analytics_page(client):
    assert b"chart.umd.min.js" not in client.get("/emi-calculator").data


def test_analytics_api_rejects_unknown_loan_type(client):
    assert client.get("/api/analytics?loan_type=Yacht%20Loan").status_code == 400


def test_analytics_api_returns_chart_data(client, fake_db):
    # The fake returns the same rows for all five queries, so one row carries every column.
    fake_db.query_result = [{
        "bank": "Punjab National Bank", "product_name": "PNB Home Loan", "loan_type": "Home Loan",
        "min_interest_rate": Decimal("8.45"), "max_interest_rate": Decimal("10.25"),
        "processing_fee_percent": Decimal("0.35"), "min_tenure_months": 60, "max_tenure_months": 360,
        "avg_rate": Decimal("8.66"), "products": 6, "total": 4,
    }]
    body = client.get("/api/analytics?loan_type=Home%20Loan").get_json()

    assert body["loan_type"] == "Home Loan"
    assert body["products"][0]["min_interest_rate"] == 8.45      # Decimal -> number
    assert body["products"][0]["max_tenure_months"] == 360
    assert body["by_type"][0]["avg_rate"] == 8.66 and body["by_bank"][0]["products"] == 6
    assert body["searches"][0]["total"] == 4 and body["saved"][0]["total"] == 4

    products_sql, params = fake_db.queries[0]
    assert params == ["Home Loan"] and "Home Loan" not in products_sql   # sent as a parameter
    assert "GROUP BY loan_type" in fake_db.queries[1][0]
    assert "GROUP BY b.bank_id" in fake_db.queries[2][0]
    assert "FROM comparison_history GROUP BY loan_type" in fake_db.queries[3][0]
    assert "FROM saved_offers" in fake_db.queries[4][0]


def read_csv(response):
    return list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))


def test_products_export(client, fake_db):
    fake_db.query_result = [{
        "bank": "State Bank of India", "bank_short_name": "SBI", "loan_type": "Home Loan",
        "product_name": "SBI Home Loan", "min_interest_rate": Decimal("8.50"),
        "max_interest_rate": Decimal("9.65"), "avg_interest_rate": Decimal("9.08"),
        "min_amount": Decimal("500000.00"), "max_amount": Decimal("100000000.00"),
        "min_tenure_months": 60, "max_tenure_months": 360, "processing_fee_percent": Decimal("0.35"),
        "processing_fee_flat": Decimal("0.00"), "source_url": "https://sbi.co.in",
        "last_updated": date(2026, 9, 30),
    }]
    res = client.get("/analytics/export/loan_products.csv")
    assert res.mimetype == "text/csv" and "attachment" in res.headers["Content-Disposition"]
    rows = read_csv(res)
    assert rows[0]["bank"] == "State Bank of India" and rows[0]["last_updated"] == "2026-09-30"
    assert "JOIN banks" in fake_db.queries[0][0]


def test_rate_history_export(client, fake_db):
    fake_db.query_result = [{
        "bank": "HDFC Bank", "loan_type": "Personal Loan", "product_name": "HDFC Personal Loan",
        "min_interest_rate": Decimal("10.85"), "max_interest_rate": Decimal("24.00"),
        "processing_fee_percent": Decimal("2.50"), "change_note": None,
        "recorded_at": datetime(2026, 9, 30, 10, 0),
    }]
    rows = read_csv(client.get("/analytics/export/rate_history.csv"))
    assert rows[0]["bank"] == "HDFC Bank" and rows[0]["change_note"] == ""
